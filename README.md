<p align="center">
	<img src="Src/Assets/min_logo.png" style="max-width: 55%;" alt="video working" />
</p>

## Streaming community downloader
<p align="center">
	<img src="Src/Assets/run.gif" style="max-width: 55%;" alt="video working" />
</p>

## Overview.
This repository provide a simple script designed to facilitate the downloading of films and series from a popular streaming community platform. The script allows users to download individual films, entire series, or specific episodes, providing a seamless experience for content consumers.

## Requirement
Make sure you have the following prerequisites installed on your system:

* python > [3.11](https://www.python.org/downloads/)
* ffmpeg [win](https://www.gyan.dev/ffmpeg/builds/)

## Installation library
Install the required Python libraries using the following command:
```bash
pip install -r requirements.txt
```

## Usage
Run the script with the following command:
```python
python run.py
```

## Auto Update
Keep your script up to date with the latest features by running:
```python
python update.py
```

## Features

### Search & Download
- **Advanced Search**: Search titles with release year displayed in results for easy identification
- **Download Single Film**: Easily download individual movies with a simple command
- **Download Specific Episodes or Entire Series**: Seamlessly retrieve specific episodes or entire series using intuitive commands. Specify a range (e.g., `0-5`), individual selections (e.g., `0,2,4`), or download all with `*`
- **Batch Download**: Download multiple films or series sequentially in a single operation

### Quality & Format
- **Automatic Quality Selection**: Automatically selects the highest available resolution (1080p > 720p > 480p)
- **MKV Container**: Downloads are saved in MKV format with embedded video and audio streams
- **AES-128 Decryption**: Handles encrypted HLS streams seamlessly with proper AES-CBC decryption
- **Audio Sync**: Perfect synchronization between video and audio during download and merge

### Organization
- **Smart Folder Structure**:
  - **Films**: `videos/<Film Name> (<Year>)/<Film Name> (<Year>).mkv`
  - **Series**: `videos/<Series Name>/Season NN/<Series Name> SNNENN.mkv`
- **Clean Naming**: Automatic removal of invalid filename characters for Windows compatibility

### Reliability
- **Automatic Retry**: Failed segments (503/429 rate limits) automatically retry with backoff strategy
- **Playwright Integration**: Uses headless browser to bypass vixcloud.co bot protection and intercept video/audio URLs
- **Session Management**: Maintains persistent session for API calls with proper token handling

### Subtitles
- **Download Subtitles**: Automatically fetch subtitles if available for downloaded content. (Note: To disable this feature, navigate to ".\Src\Lib\FFmpeg\my_m3u8" and change 'DONWLOAD_SUB' to False in the configuration file.)

## Tutorial
For a detailed walkthrough, refer to the [video tutorial](https://www.youtube.com/watch?v=Ok7hQCgxqLg&ab_channel=Nothing)

## Authors
- [@Ghost6446](https://www.github.com/Ghost6446)
