# 5.01.24 -> 7.01.24 -> 17.02.24

from Src.Util.console import console
from Src.Util.headers import get_headers
from Src.Lib.FFmpeg.util import print_duration_table

from m3u8 import M3U8 as M3U8_Lib
from tqdm.rich import tqdm
import requests, os, ffmpeg, sys, warnings, shutil, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from tqdm import TqdmExperimentalWarning
warnings.filterwarnings("ignore", category=TqdmExperimentalWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="cryptography")

MAX_WORKER = 15
DONWLOAD_SUB = True
DOWNLOAD_DEFAULT_LANGUAGE = False
SEGMENT_MAX_RETRY = 5
SEGMENT_RETRY_BACKOFF = 1.5  # seconds, multiplied by attempt number


class Decryption():
    def __init__(self, key):
        self.iv = None
        self.key = key

    def parse_key(self, raw_iv):
        if raw_iv:
            self.iv = bytes.fromhex(raw_iv.replace("0x", "").replace("0X", ""))

    def decrypt_ts(self, encrypted_data, sequence_number=None):
        if self.iv is None and sequence_number is not None:
            iv = sequence_number.to_bytes(16, byteorder='big')
        else:
            iv = self.iv

        if iv is None:
            return encrypted_data

        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        return decryptor.update(encrypted_data) + decryptor.finalize()


class M3U8_Parser:
    def __init__(self):
        self.segments = []
        self.video_playlist = []
        self.keys = []
        self.subtitle_playlist = []
        self.subtitle = []
        self.audio_ts = []

    def parse_data(self, m3u8_content):
        try:
            m3u8_obj = M3U8_Lib(m3u8_content)

            for playlist in m3u8_obj.playlists:
                self.video_playlist.append({"uri": playlist.uri})
                self.stream_infos = ({
                    "bandwidth": playlist.stream_info.bandwidth,
                    "codecs": playlist.stream_info.codecs,
                    "resolution": playlist.stream_info.resolution
                })

            for key in m3u8_obj.keys:
                if key != None:
                    self.keys = ({
                        "method": key.method,
                        "uri": key.uri,
                        "iv": key.iv
                    })

            for media in m3u8_obj.media:
                if media.type == "SUBTITLES":
                    self.subtitle_playlist.append({
                        "type": media.type,
                        "name": media.name,
                        "default": media.default,
                        "language": media.language,
                        "uri": media.uri
                    })
                else:
                    self.audio_ts.append({
                        "type": media.type,
                        "name": media.name,
                        "default": media.default,
                        "language": media.language,
                        "uri": media.uri
                    })

            for segment in m3u8_obj.segments:
                if "vtt" not in segment.uri:
                    self.segments.append(segment.uri)
                else:
                    self.subtitle.append(segment.uri)

        except Exception as e:
            console.log(f"[red]Error parsing M3U8 content: {e}")

    def get_best_quality(self):
        if self.video_playlist:
            return self.video_playlist[0].get('uri')
        console.log("[red]No video playlist found")
        return None

    def download_subtitle(self):
        path = os.path.join("videos", "subtitle")

        if self.subtitle_playlist:
            for sub_info in self.subtitle_playlist:
                name_language = sub_info.get("language")
                if name_language in ["auto", "ita"]:
                    continue
                os.makedirs(path, exist_ok=True)
                console.log(f"[green]Download subtitle: [red]{name_language}")
                req_sub_content = requests.get(sub_info.get("uri"))
                sub_parse = M3U8_Parser()
                sub_parse.parse_data(req_sub_content.text)
                url_subititle = sub_parse.subtitle[0]
                open(os.path.join(path, name_language + ".vtt"), "wb").write(requests.get(url_subititle).content)
        else:
            console.log("[red]No subtitle found")

    def get_track_audio(self, language_name):
        if self.audio_ts:
            console.log(f"[cyan]Found {len(self.audio_ts)} audio playlist(s)")
            if language_name != None:
                for obj_audio in self.audio_ts:
                    if obj_audio.get("name") == language_name:
                        return obj_audio.get("uri")
            return None
        else:
            console.log("[red]No audio playlist found")


class M3U8_Segments:
    def __init__(self, url, key=None):
        self.url = url
        self.key = key
        if key != None:
            self.decription = Decryption(key)

        self.temp_folder = os.path.abspath(os.path.join("tmp", "segments"))
        shutil.rmtree(self.temp_folder, ignore_errors=True)
        os.makedirs(self.temp_folder, exist_ok=True)

        self.progress_timeout = 30
        self.failed_segments = set()  # instance-scoped, holds segment indices (int)

    def parse_data(self, m3u8_content):
        m3u8_parser = M3U8_Parser()
        m3u8_parser.parse_data(m3u8_content)

        if self.key != None and m3u8_parser.keys:
            iv_value = m3u8_parser.keys.get("iv")
            if iv_value:
                self.decription.parse_key(iv_value)
            else:
                self.decription.iv = None  # will use per-segment sequence number

        self.segments = m3u8_parser.segments

    def get_info(self):
        response = requests.get(self.url, headers={'user-agent': get_headers()})

        if response.ok:
            self.parse_data(response.text)
        else:
            console.log(f"[red]Error fetching M3U8: {response.status_code}")
            sys.exit(0)

    def get_req_ts(self, ts_url, index):
        for attempt in range(1, SEGMENT_MAX_RETRY + 1):
            try:
                response = requests.get(ts_url, headers={'user-agent': get_headers()}, timeout=15)
                if response.status_code == 200:
                    return response.content
                if response.status_code in (429, 503):
                    # transient CDN rate-limit, retry with backoff
                    time.sleep(SEGMENT_RETRY_BACKOFF * attempt)
                    continue
                # non-transient error, no point retrying
                console.log(f"[red]Segment {index} HTTP {response.status_code}, giving up")
                break
            except Exception:
                time.sleep(SEGMENT_RETRY_BACKOFF * attempt)

        self.failed_segments.add(index)
        return None

    def save_ts(self, index, progress_counter, quit_event):
        ts_url = self.segments[index]
        ts_filename = os.path.join(self.temp_folder, f"{index}.ts")

        if not os.path.exists(ts_filename):
            ts_content = self.get_req_ts(ts_url, index)

            if ts_content is not None:
                with open(ts_filename, "wb") as ts_file:
                    if self.key:
                        decrypted_data = self.decription.decrypt_ts(ts_content, sequence_number=index)
                        ts_file.write(decrypted_data)
                    else:
                        ts_file.write(ts_content)

        progress_counter.update(1)

    def download_ts(self):
        progress_counter = tqdm(total=len(self.segments), unit="seg", desc="[yellow]Download")

        quit_event = threading.Event()
        timeout_occurred = [False]

        def timer():
            start_time = time.time()
            last_count = 0
            while not quit_event.is_set():
                current_count = progress_counter.n
                if current_count != last_count:
                    start_time = time.time()
                    last_count = current_count
                if time.time() - start_time > self.progress_timeout:
                    console.log(f"[red]No progress for {self.progress_timeout}s — stopping download")
                    timeout_occurred[0] = True
                    quit_event.set()
                    break
                time.sleep(1)
            progress_counter.refresh()

        timer_thread = threading.Thread(target=timer)
        timer_thread.start()

        try:
            with ThreadPoolExecutor(max_workers=MAX_WORKER) as executor:
                futures = []
                for index in range(len(self.segments)):
                    if timeout_occurred[0]:
                        break
                    futures.append(executor.submit(self.save_ts, index, progress_counter, quit_event))

                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        console.log(f"[red]Segment error: {e}")
        finally:
            progress_counter.close()
            quit_event.set()
            timer_thread.join()

        if self.failed_segments:
            console.log(f"[red]Failed segments after {SEGMENT_MAX_RETRY} retries: {len(self.failed_segments)} — {sorted(self.failed_segments)}")

    def join(self, output_filename):
        file_list_path = os.path.abspath("tmp_file_list.txt")

        ts_files = [f for f in os.listdir(self.temp_folder) if f.endswith(".ts")]
        ts_files.sort(key=lambda f: int(''.join(filter(str.isdigit, f))))

        with open(file_list_path, 'w', encoding='utf-8') as f:
            for ts_file in ts_files:
                abs_path = os.path.join(self.temp_folder, ts_file).replace('\\', '/')
                f.write(f"file '{abs_path}'\n")

        console.log("[cyan]Start join all file")
        try:
            ffmpeg.input(file_list_path, format='concat', safe=0).output(output_filename, c='copy', loglevel='error').run(capture_stdout=True, capture_stderr=True)
        except ffmpeg.Error as e:
            stderr = e.stderr.decode(errors='replace') if e.stderr else str(e)
            console.log(f"[red]Error saving MP4:\n{stderr}")
            sys.exit(0)

        console.log("[cyan]Clean ...")
        if os.path.exists(file_list_path):
            os.remove(file_list_path)
        shutil.rmtree("tmp", ignore_errors=True)


class M3U8_Downloader:
    def __init__(self, m3u8_url, m3u8_audio=None, key=None, output_filename="output.mp4"):
        self.m3u8_url = m3u8_url
        self.m3u8_audio = m3u8_audio
        self.key = key
        self.video_path = output_filename
        self.audio_path = os.path.abspath(os.path.join("videos", "audio.mp4"))

    def start(self):
        video_m3u8 = M3U8_Segments(self.m3u8_url, self.key)
        console.log("[green]Download video ts")
        video_m3u8.get_info()
        video_m3u8.download_ts()
        video_m3u8.join(self.video_path)
        print_duration_table(self.video_path)
        print("\n")

        if self.m3u8_audio is not None:
            audio_m3u8 = M3U8_Segments(self.m3u8_audio, self.key)
            console.log("[green]Download audio ts")
            audio_m3u8.get_info()
            audio_m3u8.download_ts()
            audio_m3u8.join(self.audio_path)
            print_duration_table(self.audio_path)
            print("\n")
            self.join_audio()

    def join_audio(self):
        base, ext = os.path.splitext(self.video_path)
        merged_path = f"{base}_merged{ext}"

        try:
            (
                ffmpeg.output(
                    ffmpeg.input(self.video_path),
                    ffmpeg.input(self.audio_path),
                    merged_path,
                    vcodec="copy",
                    acodec="copy",
                    loglevel='error'
                )
                .global_args('-map', '0:v:0', '-map', '1:a:0', '-shortest', '-strict', 'experimental')
                .run(capture_stdout=True, capture_stderr=True)
            )
            console.print("[green]Merge completed successfully.")
        except ffmpeg.Error as e:
            stderr = e.stderr.decode(errors='replace') if e.stderr else str(e)
            console.log(f"[red]Error merging audio/video:\n{stderr}")
            sys.exit(0)

        os.remove(self.video_path)
        os.remove(self.audio_path)
        os.rename(merged_path, self.video_path)


# [ main function ]
def df_make_req(url):
    response = requests.get(url)
    if response.ok:
        return response.text
    console.log(f"[red]Wrong url, error: {response.status_code}")
    sys.exit(0)

def download_subtitle(url, name_language):
    path = os.path.join("videos", "subtitle")
    os.makedirs(path, exist_ok=True)
    console.log(f"[green]Download subtitle: [red]{name_language}")
    open(os.path.join(path, name_language + ".vtt"), "wb").write(requests.get(url).content)

def download_m3u8(m3u8_playlist=None, m3u8_index=None, m3u8_audio=None, m3u8_subtitle=None, key=None, output_filename=os.path.join("videos", "output.mp4"), log=False):

    key = bytes.fromhex(key) if key is not None else key

    if m3u8_playlist != None:
        console.log("[green]Download m3u8 from playlist")

        parse_class_m3u8 = M3U8_Parser()
        if "#EXTM3U" not in m3u8_playlist:
            parse_class_m3u8.parse_data(df_make_req(m3u8_playlist))
        else:
            parse_class_m3u8.parse_data(m3u8_playlist)

        if DOWNLOAD_DEFAULT_LANGUAGE:
            m3u8_audio = parse_class_m3u8.get_track_audio("Italian")
            console.log(f"[green]Select language => [purple]{m3u8_audio}")

        if m3u8_index == None:
            m3u8_index = parse_class_m3u8.get_best_quality()
            if m3u8_index and "https" in m3u8_index:
                if log: console.log(f"[green]Select m3u8 index => [purple]{m3u8_index}")
            else:
                console.log("[red]Cant find a valid m3u8 index")
                sys.exit(0)

        if DONWLOAD_SUB:
            parse_class_m3u8.download_subtitle()

    if m3u8_subtitle != None:
        parse_class_m3u8_sub = M3U8_Parser()
        if "#EXTM3U" not in m3u8_subtitle:
            parse_class_m3u8_sub.parse_data(df_make_req(m3u8_subtitle))
        else:
            parse_class_m3u8_sub.parse_data(m3u8_subtitle)
        if DONWLOAD_SUB:
            parse_class_m3u8_sub.download_subtitle()

    path = output_filename.split("\\")
    os.makedirs("\\".join(path[:-1]), exist_ok=True)
    if log: console.log(f"[green]Download m3u8 from index => [purple]{m3u8_index}")
    M3U8_Downloader(m3u8_index, m3u8_audio, key=key, output_filename=output_filename).start()
