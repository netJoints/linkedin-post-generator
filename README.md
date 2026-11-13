# linkedin-post-generator

A local writing and video desk for LinkedIn. It runs on your laptop, calls [Ollama](https://ollama.com) on `127.0.0.1` for the writing, and makes videos and cards with ffmpeg and the browser. The draft is not sent to a cloud model. Nothing is posted to LinkedIn; you paste and upload the results yourself.

- **Project pages:** [slides](https://netjoints.github.io/linkedin-post-generator/) · [why the cards](https://netjoints.github.io/linkedin-post-generator/cards/)
- **Source:** [github.com/netJoints/linkedin-post-generator](https://github.com/netJoints/linkedin-post-generator)

## Contents

- [What it makes](#what-it-makes)
- [Requirements](#requirements)
- [Install](#install)
- [Run it](#run-it)
- [The five modes](#the-five-modes)
- [Voices: AI voiceover and My voice](#voices-ai-voiceover-and-my-voice)
- [Music](#music)
- [How a request works](#how-a-request-works)
- [Limits](#limits)
- [Tests and continuous integration](#tests-and-continuous-integration)
- [Project layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [Security and privacy](#security-and-privacy)

## What it makes

From one draft and the sources you give it, the app can produce:

| Output | Made by | Needs |
| --- | --- | --- |
| A longer article, `linkedin-article.txt` | Ollama | Ollama and a model |
| A shorter feed post, `linkedin-post.txt`, written as the video caption with no URLs | Ollama | Ollama and a model |
| A first comment listing the links you supplied, `linkedin-comment.txt` | The app | Nothing |
| Swipeable cards as a PDF, a PNG zip, or a wide article cover | The browser | Nothing |
| An animated explainer MP4, with a headline, connecting nodes, and a changing bottom line | The browser and ffmpeg | ffmpeg for the file |
| A picture video with music and an optional voiceover | The browser and ffmpeg | ffmpeg |
| A motion film in one of several 1080 × 1350 formats | The browser and ffmpeg | ffmpeg for the file |

Everything that is not the writing happens in the browser or in ffmpeg on this laptop. Ffmpeg is needed only to save a video file. Play previews still work without it.

## Requirements

| Requirement | Notes |
| --- | --- |
| Laptop | macOS, Linux, or Windows. The checked-in `start.sh` is for macOS and Linux. The development was done on an Apple Silicon Mac. |
| Memory | 16 GB is enough for Gemma 4 12B. Mistral Small 3.2 is a 15 GB model and is comfortable on 24 GB. On 16 GB it will be slow or fail to load. |
| Free disk | About 8 GB for Gemma, about 15 GB for Mistral, plus a few GB of overhead. The optional local voices add about 0.6 GB for Kokoro (environment and model files) and about 4 GB for Chatterbox (PyTorch environment and model cache). |
| Python | 3.10 or newer for the app. The app uses the standard library only. |
| Ollama | 0.31.0 or newer. Gemma 4 12B refuses to load on older releases. |
| ffmpeg | Needed to save any MP4. Install with `brew install ffmpeg` on macOS, or your package manager on Linux. |
| Network | `ollama pull` and the voice model downloads happen once. After that, generation and voices run on this machine. Each pasted link and YouTube transcript is fetched from this laptop when you write a draft. That fetch is not a cloud LLM. |

No database, Docker, or API key is required for the core app.

## Install

### 1. Ollama and the writing models

1. Install Ollama from [https://ollama.com/download](https://ollama.com/download).
2. Open the Ollama app, or start the server yourself:

   ```bash
   ollama serve
   ```

3. Confirm it answers:

   ```bash
   ollama --version
   curl -sf http://127.0.0.1:11434/api/tags
   ```

4. Pull at least one model. The page lists both and disables any model that is not installed.

   ```bash
   ollama pull mistral-small3.2
   ollama pull gemma4:12b
   ```

   | Menu name | Ollama tag | Download | What it is |
   | --- | --- | --- | --- |
   | Mistral Small 3.2 (24B) | `mistral-small3.2` | about 15 GB | Stronger instruction following and a 128K context window. Prefer it with 24 GB of memory. |
   | Gemma 4 12B | `gemma4:12b` | about 8 GB | Faster and lighter. Prefer it on a 16 GB laptop. |

5. Check what is on disk with `ollama list`. You should see `mistral-small3.2:latest`, `gemma4:12b`, or both.

Leave Ollama running while you use the app. The draft server only talks to `http://127.0.0.1:11434`.

### 2. ffmpeg

```bash
brew install ffmpeg
```

Check it with `ffmpeg -version`. The server looks for `ffmpeg` and `ffprobe` on the PATH, and also next to the Homebrew binary at `/opt/homebrew/bin`.

### 3. This app

```bash
git clone https://github.com/netJoints/linkedin-post-generator.git
cd linkedin-post-generator
```

There is nothing to `pip install` for the app. `requirements.txt` says so. The optional voices have their own environments; see [Voices](#voices-ai-voiceover-and-my-voice).

## Run it

On macOS or Linux:

```bash
chmod +x start.sh
./start.sh
```

`start.sh` checks Python, checks that Ollama is running, checks that the expected models are installed, then starts the server. If a model is missing it prints the `ollama pull` command and exits. It does not check for ffmpeg.

On any system, after those checks:

```bash
python3 server.py
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765).

The server listens on `127.0.0.1` only, so other machines on your network cannot open it. Stop it with Ctrl+C in its terminal.

## The five modes

The first question on the form is **What to make**.

### Full draft

1. Enter a company (optional), one to 12 topics, optional instructions, up to five links, and optionally one PDF, Word, or text file.
2. Choose **Mistral Small 3.2** or **Gemma 4 12B**, then click **Write drafts**. The first reply after a cold start is slower because Ollama loads the model.
3. The model writes the article and the short post. A second, shorter request asks the same model for the card text. If that reply is unusable, the cards are built from the draft text.
4. Copy or download the article, the short post, and, when you supplied links, the first comment.
5. Download the cards and, with ffmpeg, the MP4s. The file names come from the company and topics, so two drafts do not overwrite each other. For example, company `Cisco` and topic `live protect` save as `blog-cisco-live-protect.pdf`, `blog-cisco-live-protect.zip`, `blog-cisco-live-protect-cover.png`, `blog-cisco-live-protect.mp4`, and `blog-cisco-live-protect-explainer.mp4`.

Field notes:

- **Company** is optional. The model may use the name. It does not invent products, announcements, or metrics unless you state them, or a source says so. The name is not printed on the cards.
- **Topics** are required and kept short. Separate them with commas or new lines. A sentence here is treated as the subject, not as a request.
- **Instructions** (up to 1,200 characters) say what the post should do, such as announcing an event and inviting people. The app does not search the web, so a line that says to check a site does nothing unless that page is in Links.
- **Links** (up to five, one per line) are checked before they are opened. A public web page is read as text. A YouTube watch, `youtu.be`, or shorts link includes its transcript when captions exist. A Vimeo link contributes the title only. A channel or playlist page is not one video.
- **Reference file** (one PDF, DOC, DOCX, or TXT up to 8 MB) is read in memory, used as background with the links, and not saved. A scanned PDF with no text layer cannot be read.

The **cards** are a set of 6 to 10 designed pages drawn at 1080 × 1350: a hook, one idea per card, a checklist, and a close. The page can export a PDF for LinkedIn’s document post, a PNG per card for a multi-image post, a hook image, and a wide cover for the article. The reasoning behind the card format is on the [cards page](https://netjoints.github.io/linkedin-post-generator/cards/).

### Animated video only

No model is called in this mode.

1. Write one script per card. The page starts with six cards and **Add a card** goes up to ten. Each card plays for about 11 seconds, so six cards make about 66 seconds. An empty card is skipped.
2. Leave the layout on **Auto**, or pick one. Auto reads the script:
   - **Statement**: one sentence, shown large.
   - **Question**: a question. "The scan, or the change window?" shows both choices.
   - **Steps**: numbered lines, or lines that start with first, then, or finally.
   - **Checklist**: bullet lines, or lines that start with a verb such as Log, Keep, or Scope.
   - **Compare**: a problem, then a line that starts with "That is why", "Instead", or "But". `Before:` and `After:` lines become two labeled columns.
   - **Diagram**: three or more short sentences, connected as boxes around a centre box.

   A short first line of four words or fewer is the small label. A first line with no period is the title. A picked layout that does not fit the script falls back to Auto, and the card says so.
3. Click **Plan the video**. The page lists each card with its layout and words. A card with too few words is listed with the reason and left out.
4. Click **Play card** or **Play all**, then **Download full video** to save one MP4 of every planned card in order. The file name comes from the first card. Playback works without ffmpeg.

`POST /api/scenes` plans the cards without fetching links or calling Ollama. `POST /api/stitch` joins up to ten card MP4s with ffmpeg.

### Post via Pics

Turn a set of pictures into one post and one MP4.

1. Add up to **10 pictures**. JPEG, PNG, WebP, GIF, and SVG are accepted; an animated GIF uses its first frame. Drag a row, or use Up and Down, to set the order.
2. Each picture stays on screen for about **8 seconds**. Choose a **transition** between pictures: Crossfade (the default), Slide, Wipe, Push, or Zoom. Each transition takes 0.7 seconds.
3. Write or edit the post text. The video carries the post’s words on the pictures, and a URL is left out so LinkedIn does not turn the post into a link preview.
4. Pick a **background music** track, and a **volume**: Low, Medium (default), or High. See [Music](#music).
5. Pick a **voiceover**: None, **My recording** (an audio file you choose, played as it is), or **Read the post aloud** (an AI voice, including **My voice**). See [Voices](#voices-ai-voiceover-and-my-voice).
6. Click **Read the pictures**. The pictures go to the selected Ollama model, which writes the post from them. Only a model that accepts images can do this. Check that the model reads your pictures before you rely on it. The pictures are not saved.
7. Play the sequence, then download the MP4 when ffmpeg is installed.

When the video is joined with a voiceover, the voice is trimmed to the length of the pictures. The pictures keep their length, so a longer post is cut at the end. Keep the post to about the length of the pictures, or use fewer words.

### Picture video

Up to **12 pictures**, each with its own short caption. Each picture is about 3.5 seconds, in a portrait frame that fills a phone. Play checks the sequence, and **Download video** saves an MP4. The pictures are not saved.

### Motion film

Pick one of the formats, fill in its lines, then play it or save it as a 1080 × 1350 MP4. The formats are:

- **Line film**: an event or launch recap.
- **Quote**: a line someone said. Quote only what was really said.
- **Big number**: one figure that matters. Use only numbers you can stand behind.
- **Word swap**: not this, not this, this.
- **Before and after**: the change you made.
- **Hook cuts**: stop the scroll.

## Voices: AI voiceover and My voice

The **Read the post aloud** option uses a local AI voice. It does not use the Mac’s built-in voices. Three choices appear in the voice list:

| Choice | Engine | Licence | Notes |
| --- | --- | --- | --- |
| Heart, Bella, Nicole, Michael (US); Emma, George (UK) | [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) through `kokoro-onnx` | Apache-2.0 | Fast, natural, and small. Runs on the CPU in seconds. |
| Chatterbox, default voice | [Chatterbox](https://github.com/resemble-ai/chatterbox) by Resemble AI | MIT | Slower. On an Apple M4 Pro, a 6-second clip took about 30 seconds to make after a 9-second model load. Every output carries an inaudible Resemble AI watermark. |
| Chatterbox, my voice | Chatterbox, with your saved sample | MIT | Appears after you save a voice sample. See [My voice](#my-voice). |

The text is cleaned before it is read: links, hashtags, and symbols are removed, and each line break becomes a short pause. The post is read up to 4,000 characters.

Voices that are not installed are hidden from the list, so the list always shows only what will work.

### Setting up Kokoro

Kokoro runs in its own environment under `~/.linkedin-tts`, outside the repo.

```bash
mkdir -p ~/.linkedin-tts && cd ~/.linkedin-tts
python3 -m venv venv
./venv/bin/pip install kokoro-onnx==0.4.7 soundfile==0.14.0 onnxruntime==1.32.0
curl -L -o kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -L -o voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```

The model files are about 325 MB and 28 MB. The app uses `tts_kokoro.py`, which reads the text on stdin and writes a WAV on stdout.

### Setting up Chatterbox

Chatterbox needs Python 3.11 (the version this was tested with) and PyTorch. It runs in its own environment.

```bash
cd ~/.linkedin-tts
uv venv --python 3.11 chatterbox-venv
uv pip install --python chatterbox-venv/bin/python chatterbox-tts==0.1.7 "setuptools<80" truststore
```

`setuptools<80` is needed because the watermark module imports `pkg_resources`. `truststore` lets the model download use the system certificate store, which corporate networks often require.

The model is downloaded once, and the app then runs fully offline (`HF_HUB_OFFLINE=1`):

```bash
HF_HUB_DISABLE_XET=1 ~/.linkedin-tts/chatterbox-venv/bin/python -c "
import truststore; truststore.inject_into_ssl()
from chatterbox.tts import ChatterboxTTS
ChatterboxTTS.from_pretrained(device='cpu')
print('Chatterbox model is cached.')
"
```

The first download is about 3 GB. `HF_HUB_DISABLE_XET=1` avoids the new Hugging Face storage path, which some networks block. Leave it on if the download works without it, or if you see a 403 error.

Once `~/.cache/huggingface/hub/models--ResembleAI--chatterbox` exists, the Chatterbox voices appear in the list.

### My voice

**My voice** lets Chatterbox speak with your voice. You save one sample, and the app reuses it for every video until you replace or delete it.

Chatterbox does not train a model on your voice. The saved sample is a reference clip that the model copies the voice from on each run. That is why saving takes seconds, and why the sample quality matters more than its length.

How to use it:

1. In the **My voice** panel, click **Choose sample** and pick a recording of you reading aloud. Record 15 to 30 seconds in a quiet room, with the phone or laptop a short distance from your mouth. Any common audio file works (MP3, M4A, WAV, WebM, and others).
2. Click **Save my voice**. The app converts the file to mono 24 kHz WAV, keeps the first 20 seconds, and rejects recordings shorter than 5 seconds.
3. **Chatterbox, my voice** now appears in the voice list. Pick it under **Read the post aloud**. It uses the saved sample automatically, and you do not upload it again.
4. To **re-learn** the voice, record a better sample and save it. The new file replaces the old one. The button then reads **Re-learn my voice**.
5. To remove it, click **Forget my voice**. The file is deleted and the option disappears from the list.

The sample is stored at `~/.linkedin-tts/my-voice/reference.wav`, outside the repo, so it is never committed. Only you have access to it on this laptop. Delete it with **Forget my voice**, or remove the folder.

Only use a sample of your own voice, or a voice you have permission to copy. The app has no way to check that for you.

## Music

Pick a background track under **Post via Pics**:

| Track | File |
| --- | --- |
| Meditating Beat (default) | `static/music/beat.m4a` |
| River Meditation | `static/music/river.m4a` |
| Inspiration | `static/music/inspiration.m4a` |
| Inventing Flight | `static/music/inventing.m4a` |
| Energizing | `static/music/energizing.m4a` |
| Celebration | `static/music/celebration.m4a` |

Each track is a public-domain CC0 recording from [FreePD.com](https://freepd.com), taken from the Internet Archive item [abook-music-freepd-cc0](https://archive.org/details/abook-music-freepd-cc0). CC0 does not require credit. The licence notes are in `static/music/CREDITS.txt`. Each file is the first 100 seconds, saved as AAC and levelled so it sits quietly under a picture video.

The volume options are Low, Medium (default), and High. The track is looped to the length of the video, faded in and out, and ducked under the voiceover, so the speech stays clear.

Only tracks with a licence that allows reuse are included. Music is not taken from YouTube.

## How a request works

1. The browser posts the form to `POST /api/generate` on this laptop.
2. Each link is checked before it is opened. Only `http` and `https` are allowed. Links with a username or password are rejected. Loopback, private, link-local, and other non-public addresses are rejected.
3. Page text is extracted locally and capped. A YouTube link is handled separately: the app asks YouTube’s player endpoint for a caption track and downloads it. A caption address is opened only when its host is YouTube or Google video. An attached file is extracted in memory the same way.
4. The prompt goes to Ollama’s chat API. Gemma’s thinking mode is turned off, so the reply is the draft and not a reasoning trace.
5. The reply is split into the article and the short post, and streamed back to the page. URLs are removed from the short post. The supplied links become the first comment.
6. A second, shorter request asks the same model for the card text. The cards may only restate the draft. A number that was not in the draft drops the model’s cards, and the page builds them from the draft instead.

For video, the browser draws each frame as a JPEG and posts them to `POST /api/stitch`, or to the other video routes. The server writes the frames into a temporary folder, runs ffmpeg there, and deletes the folder afterward. Music and voice are mixed in the same ffmpeg command. Music is taken from the bundled files only. The voice is read by a local helper, and its audio is mixed with the music under the speech.

`GET /api/health` reports whether Ollama is up and which of the two models are installed. `GET /api/voices` lists the voices that are ready, and `GET /api/my-voice` reports whether a voice sample is saved.

## Limits

- Five links. Each read is capped at about 500 KB and 12 seconds.
- About 4,000 characters are kept from each page.
- About 8,000 characters are kept from each YouTube transcript. Videos without captions, and Vimeo links, contribute the title only.
- One attachment, up to 8 MB. About 8,000 characters of its text are kept. Encrypted PDFs and scans without a text layer are rejected.
- Topics, the company field, and the instructions are length-capped. Instructions stop at 1,200 characters.
- Post via Pics takes up to 10 pictures. Picture video takes up to 12. Motion cards and card joins take up to 10 MP4 files.
- A voiceover is trimmed to the length of the pictures.
- Read the post aloud reads up to 4,000 characters. Chatterbox is several times slower than real time, so a long post can take minutes to voice. Kokoro is much faster.
- The app does not search the web, and the model can still be vague or wrong. Read every draft before you post it.
- Generation time depends on the laptop. Gemma on Apple Silicon with the model loaded often finishes in under a minute. Mistral Small 3.2 takes longer and uses most of a 24 GB machine.

## Tests and continuous integration

Install the test tools, then run the suite from the repo root:

```bash
python3 -m pip install pytest flake8
pytest
```

`pytest.ini` puts the repo on the import path. Some tests render MP4 files, so they need ffmpeg. The voice tests write to a temporary folder, not to your saved voice sample.

| File | What it checks |
| --- | --- |
| `tests/test_links.py` | Links, transcripts, and drafts, without calling Ollama |
| `tests/test_cards.py` | Card text, fallback decks, and video frames |
| `tests/test_motion.py` | Explainer storyboards and frames |
| `tests/test_scenes.py` | Card layouts, timing, and joining |
| `tests/test_stills.py` | Picture video frames and captions |
| `tests/test_picture_video.py` | Post via Pics: scale, music, voiceover, and speech limits |
| `tests/test_my_voice.py` | Saving, re-learning, forgetting, and refusing bad recordings |

### GitHub Actions

The workflow is in `.github/workflows/python-app.yml`. It runs on every push to `main` and on every pull request to `main`. It has one job, **Lint and test**, which:

1. Checks out the repo and sets up Python 3.10.
2. Installs `flake8`, `pytest`, and the requirements file, which is empty.
3. Runs `flake8` with the blocking checks for syntax errors and undefined names. A second `flake8` pass only reports style warnings and never fails the run.
4. Runs `pytest`.

The Actions runner is Ubuntu, which includes ffmpeg. The job does not download the voice models or call Ollama, so it runs without them. The run result appears on the pull request as the **Lint and test** check.

## Project layout

```
server.py                 local web server, routes, and multipart parsing
cards.py                  card text from the draft, with a local-model pass in front
media.py                  ffmpeg: MP4 joins, music, voiceover mix, My voice, local voices
pictures.py               Post via Pics: the post from pictures, using the local vision model
stills.py                 picture video with captions
motion.py                 explainer storyboard from the draft, a script, or one card
documents.py              PDF, Word, and text attachment reading
youtube.py                YouTube transcript reading
tts_kokoro.py             Kokoro helper, run by its own Python with the text on stdin
tts_chatterbox.py         Chatterbox helper, run by its own Python with the text on stdin
start.sh                  prerequisite checks, then python3 server.py
requirements.txt          a note that the app needs no third-party packages
pytest.ini                lets the tests import the app
static/index.html         the form
static/app.js             the draft page: streaming, copy, and download
static/cards.js           card drawing, PDF, PNG zip, and the video request
static/motion.js          explainer drawing
static/script.js          animated video from one script per card
static/pics.js            Post via Pics: pictures, music, voiceover, My voice
static/stills.js          picture video with captions
static/reel.js            motion film formats
static/music/             six CC0 music tracks and CREDITS.txt
static/styles.css
tests/                    the test files listed above
docs/                     GitHub Pages: the slide deck (docs/) and the cards page (docs/cards/)
.github/workflows/        GitHub Actions: lint and test
```

## Troubleshooting

**The page says Ollama is not running.** Open the Ollama app, or run `ollama serve`, then reload [http://127.0.0.1:8765](http://127.0.0.1:8765).

**A model is greyed out.** It is not in `ollama list`. Pull it with the command in the install section.

**`gemma4:12b` fails to load.** Upgrade Ollama to 0.31.0 or newer (`ollama --version`), then pull the model again.

**Port 8765 is already in use.** Stop the other copy of `server.py`, or change `PORT` in `server.py` and open that port.

**A link is rejected.** Use a public `https://` URL with no username or password. Internal hostnames and `localhost` are blocked on purpose.

**A YouTube link says "title only, no transcript."** The video has no captions, or YouTube refused the caption track. The draft still runs from the title. After you pull a new version, stop the old `server.py` and start it again.

**The short post is missing.** The article is still shown. Run it again. A smaller model is more likely to skip the second section.

**The video button is missing.** ffmpeg is not on the PATH. Install it, reload the page, and write the draft again. The PDF, the images, and the article cover do not need ffmpeg.

**The voice list has no Chatterbox voices.** The Chatterbox environment or its model cache is missing. Follow the Chatterbox setup. The list shows only voices that are ready.

**Chatterbox fails with a certificate error, or a 403 while downloading.** Run the one-time download with `truststore` and `HF_HUB_DISABLE_XET=1`, as in the setup section.

**Chatterbox is slow.** Expected on Apple Silicon. Use Kokoro for quick drafts and Chatterbox for the final version.

**The voice is cut off.** The voice is trimmed to the picture length. Shorten the post, or add pictures.

**"My voice" is not in the list.** Save a sample first. The option appears after a sample is saved.

**My voice sounds wrong.** Re-learn it with a longer, cleaner recording, with no music or fans behind it, and about 15 to 30 seconds of speech.

**The cards look plain.** They are type, not a generated photograph. LinkedIn document posts that get read are large words on a steady layout.

**The laptop fans stay loud.** That is the model running on the CPU or GPU. Close other large apps before using Mistral Small 3.2 or Chatterbox.

## Security and privacy

- No API keys, tokens, or passwords are stored in the repo. Ollama on localhost does not need a key. The card drawing and the PDF stay in the browser.
- The fetcher does not accept credentials in a URL. YouTube transcripts are read without an API key and without browser cookies. A caption address from the player response is opened only after the same public-address check as any other link, and only when the host is YouTube or Google video.
- An attached file is read in memory and discarded. The original is not written to disk. Only PDF, Word (`.doc`, `.docx`), and `.txt` contents are accepted, and only after the bytes match that type.
- Video files are made in a temporary folder that is deleted afterward. Uploaded recordings are passed to ffmpeg as data, never as a command line or a path.
- The voice sample is stored outside the repo, in `~/.linkedin-tts/my-voice/`. Remove it with **Forget my voice**.
- The local voices run offline. Their models are read from the Hugging Face cache, and `HF_HUB_OFFLINE=1` is set so nothing is downloaded while a video is made.
- The voice models in use are Kokoro (Apache-2.0) and Chatterbox (MIT), both licensed for commercial use. Other voice models were reviewed and left out: Breeze TTS 2, Fish Audio S2 Pro, OmniVoice, and F5-TTS, because their weights are limited to research or non-commercial use. Qwen3-TTS was left out under the project's rule against Chinese-hosted models.
- Do not paste customer data or other sensitive material if that conflicts with the rules of the machine you are using. The prompt and the model stay on the laptop, but the text is still processed by local software you installed.
