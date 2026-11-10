# LinkedIn drafts

A local writing desk for LinkedIn. It runs on your laptop, calls [Ollama](https://ollama.com) on `127.0.0.1`, and does not send the draft to a cloud model.

You give it a company name (optional), one or more topics, optional instructions for what the post should do, up to five links (optional), and one PDF, Word, or text file (optional). A YouTube link can include its transcript. It writes two plain-text pieces you can paste into LinkedIn, then a set of swipeable cards from that same draft:

- a longer article
- a shorter feed post, written as the caption for the video
- portrait cards for that video, plus a wide cover for the article
- an animated explainer from the same draft: a headline, nodes that connect, and a bottom line that changes

Choose **Animated video only** to skip the article and the cards. Write a script for each card, six or more, and the page picks a layout for each one from its words. The cards play in order as one MP4, about 11 seconds per card. That path does not call Ollama.

There is no database. Drafts are not saved on the server. Copy or download them from the page. The cards are drawn in the browser. No image service is called, and no API key is stored.

## What you need

| Requirement | Notes |
| --- | --- |
| Laptop | macOS, Linux, or Windows. The checked-in start script is for macOS and Linux. |
| Memory | 16 GB is enough for Gemma 4 12B. Mistral Small 3.2 is a 15 GB model and is comfortable on 24 GB. On a 16 GB machine it will be slow or fail to load. |
| Free disk | About 8 GB for Gemma, about 15 GB for Mistral, plus a few GB of overhead. Pull both only if you have about 30 GB free. |
| Python | 3.10 or newer. The app uses the standard library only. |
| Ollama | 0.31.0 or newer. Gemma 4 12B refuses to load on older releases. |
| Network | `ollama pull` downloads the model weights once. After that, generation stays on this machine. Each pasted link, and each YouTube transcript, is fetched from this laptop when you write a draft. That fetch is not a cloud LLM. |

No vector database, SQLite, Docker, or API key is required.

## Install Ollama

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

Leave Ollama running while you use this tool. The draft server only talks to `http://127.0.0.1:11434`.

## Install the models

Pull at least one of these. The page lists both and disables any model that is not installed.

```bash
ollama pull mistral-small3.2
ollama pull gemma4:12b
```

| Menu name | Ollama tag | Download | What it is |
| --- | --- | --- | --- |
| Mistral Small 3.2 (24B) | `mistral-small3.2` | about 15 GB | Stronger instruction following and a 128K context window. Prefer this when the laptop has 24 GB of memory. |
| Gemma 4 12B | `gemma4:12b` | about 8 GB | Faster and lighter. Prefer this on a 16 GB laptop. |

Check what is on disk:

```bash
ollama list
```

You should see `mistral-small3.2:latest`, `gemma4:12b`, or both.

## Get this app

```bash
git clone https://github.com/netJoints/linkedin-post-generator.git
cd linkedin-post-generator
```

There is nothing to `pip install`. `requirements.txt` is only a note that the dependency list is empty.

## Run it

macOS or Linux:

```bash
chmod +x start.sh
./start.sh
```

`start.sh` checks Python, checks that Ollama is running, checks that at least the expected model names are installed, then starts the server. If a model is missing it prints the `ollama pull` command and exits.

Any operating system, after the checks above are already done:

```bash
python3 server.py
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765).

The server listens on `127.0.0.1` only. Other machines on the network cannot open it. Stop it with Ctrl+C in that terminal.

## Slides

The same story as an animated deck: [netjoints.github.io/linkedin-post-generator](https://netjoints.github.io/linkedin-post-generator/).

Arrow keys or a click move between slides. F is fullscreen. N opens speaker notes. O opens the overview. The deck is static HTML in `docs/`. It does not run the draft server.

## Why the cards

The research note behind the swipeable cards is a normal web page, not a Cursor link: [netjoints.github.io/linkedin-post-generator/cards/](https://netjoints.github.io/linkedin-post-generator/cards/).

It lives at `docs/cards/index.html` and is published with the rest of the GitHub Pages site. It compares LinkedIn formats, shows the card sequence, and explains why the PDF, the images, and the video stay on this laptop.

## Use the form

1. Choose **Full draft** or **Animated video only**. Full draft uses **Mistral Small 3.2** or **Gemma 4 12B**. Animated video only uses the script you paste and does not call a model.
2. Company name is optional. Example: `Cisco`. The model may mention that name in the article or the short post. It does not invent products, announcements, or metrics unless you state them in the instructions or a source says so. The name is not printed on the cards.
3. Topics are required. Keep them short. Separate them with commas or new lines. Example: `AgenticOps, AI security`. Up to 12 topics. A sentence in this box is treated as the subject, not as a request.
4. Instructions are optional, up to 1,200 characters. This is one brief for what the post should do, such as announcing an event and inviting people to particular sessions. It is not a chat, and it does not send the model to search the web. A fact you state here can be repeated. A fact you do not state, and that is not in a link or the file, is left out.
5. Links are optional, one per line, up to five. A normal web page or blog post is fetched and trimmed to text. A YouTube watch link, a `youtu.be` link, or a shorts link includes the transcript when YouTube provides captions. English is preferred, then any other language. A Vimeo link contributes the video title and author only. A channel or playlist page does not.
6. A reference file is optional. Choose one `.pdf`, `.doc`, `.docx`, or `.txt` file, up to 8 MB. Its text is read on this laptop and used with the links. The file is not saved. A scanned PDF with no text layer cannot be read.
7. Click **Write drafts**. The first reply after a cold start is slower because Ollama loads the model into memory. After the text is written, the same model designs the cards. If that reply is unusable, the cards are built from the draft text instead.
8. Copy or download the article (`linkedin-article.txt`), the short post (`linkedin-post.txt`), and, when you supplied links, the first comment (`linkedin-comment.txt`).
9. Download the cards. The file name is built from the company and the topics, so two blogs do not overwrite each other. Company `Cisco` and topic `live protect` save as `blog-cisco-live-protect.pdf`, `blog-cisco-live-protect.zip`, `blog-cisco-live-protect-cover.png`, and, when ffmpeg is installed, `blog-cisco-live-protect.mp4` and `blog-cisco-live-protect-explainer.mp4`. **Download animated video** is the diagram: the headline stays, nodes connect one beat at a time, and the line at the bottom changes. **Download video** holds each card for about four seconds. **Download images** is a zip of PNGs for a multi-image post. **Article cover** is a wide PNG for the long article. **Download PDF** is the file for LinkedIn’s document button. Play explainer previews the diagram before you download it.

## Animated video only

1. Choose **Animated video only**.
2. Write one script per card. The page starts with six cards. **Add a card** goes up to ten. Each card plays for about 11 seconds, so six cards make a video of about 66 seconds. An empty card is skipped.
3. Leave the layout on **Auto**, or pick one. Auto reads the script:
   - **Statement**: one sentence, shown large.
   - **Question**: a question. "The scan, or the change window?" shows both choices.
   - **Steps**: numbered lines, or lines that start with first, then, finally.
   - **Checklist**: bullet lines, or lines that start with a verb such as Log, Keep, or Scope.
   - **Compare**: a problem, then a line that starts with "That is why", "Instead", or "But". `Before: …` and `After: …` lines become two labeled columns.
   - **Diagram**: three or more short sentences, connected as boxes around a center box.

   A short line at the top of a card, of four words or fewer, is the small label. A first line with no period is the title. A picked layout that does not fit the script falls back to the Auto choice, and the card says so.
4. Click **Plan the video**. The page lists each card with its layout and its words. Pick a card to see it. A card with too few words is listed with the reason and left out of the video.
5. Click **Play card** or **Play all**. Click **Download full video** to save one MP4 of every planned card, in order. Each card is drawn and encoded on its own, then the cards are joined. The file name comes from the first card, such as `explainer-autonomy-must-earn-trust-every-time-it-acts.mp4`. Playback works without ffmpeg. The file needs ffmpeg.

`POST /api/scenes` plans the cards. It does not fetch links and does not call Ollama. Each card stops at 1,200 characters. `POST /api/stitch` joins up to ten card MP4s with ffmpeg on this laptop. The joined file keeps the order of the cards. The words on screen come only from each card's script.

Paste the text into LinkedIn yourself, and upload the file yourself. This app does not log in to LinkedIn and does not publish. Use the short post as the video caption. It has no URLs in it. After the post is published, paste the first comment, which lists the links you supplied. From a personal profile, a video, the image zip, the article, and a text post can be boosted. A PDF document post cannot. A URL in the caption makes LinkedIn attach a link preview, and a link post is the weakest format on the chart in `docs/cards/`.

## How a request works

1. The browser posts the form to `POST /api/generate` on this laptop.
2. Each link is checked before it is opened. Only `http` and `https` are allowed. Links with a username or password are rejected. Loopback, private, link-local, and other non-public addresses are rejected.
3. Page text is extracted locally and capped so the prompt stays bounded. A YouTube link is handled separately: the app asks YouTube's player endpoint for a caption track and downloads that track. The caption address is opened only when its host is YouTube or Google video. If a file was attached, its text is extracted in memory the same way and added as another source. PDF, Word, and text files are parsed as data. They are not opened in an editor and not saved.
4. The prompt is sent to Ollama's chat API. Gemma's thinking mode is turned off so the reply is the draft, not a reasoning trace.
5. The reply is split into the article and the short post and streamed back to the page. URLs are removed from the short post. The links you supplied are listed as a first comment. Those pieces are shown while a second, shorter request asks the same local model for the card text. The cards may only restate the draft. A number that was not in the draft drops the model’s cards, and the page builds them from the draft instead. The browser then draws each card at 1080×1350.

`GET /api/health` reports whether Ollama is up and which of the two models are installed. The page calls that when it loads.

## Limits

- Five links, each read is capped at about 500 KB and 12 seconds.
- About 4,000 characters of text are kept from each page.
- About 8,000 characters of each YouTube transcript are kept. Videos without captions, and Vimeo links, contribute the title only.
- One attachment, up to 8 MB. About 8,000 characters of its text are kept. Encrypted PDFs, and scans without a text layer, are rejected.
- Topics, the company field, and the instructions are length-capped. Instructions stop at 1,200 characters.
- The app does not search the web. A line in the instructions that says to check a website does nothing unless that page is in Links.
- The model can still be vague or wrong. Read the draft before you post it. If you did not supply a source, the model is writing from the topic names and the instructions only.
- A YouTube video with no captions, or a transcript YouTube refuses to serve, is used as a title only. The draft still runs.
- Generation time depends on the laptop. Gemma on an Apple Silicon machine with the model already loaded often finishes in under a minute. Mistral Small 3.2 takes longer and uses most of a 24 GB machine while it runs. The cards are a second pass after that, so the page stays on “Designing the cards” for a bit.
- The deck is 6 to 10 cards: a hook, one idea per card, a short checklist, and the question from the draft. It does not invent a statistic to make a card look busier.

## Troubleshooting

**The page says Ollama is not running.** Open the Ollama app, or run `ollama serve`, then reload [http://127.0.0.1:8765](http://127.0.0.1:8765).

**A model is greyed out.** It is not in `ollama list`. Pull it with the command in the table above.

**`gemma4:12b` fails to load.** Upgrade Ollama to 0.31.0 or newer (`ollama --version`), then pull the model again.

**Port 8765 is already in use.** Stop the other copy of `server.py`, or change `PORT` in `server.py` and open that port instead.

**A link is rejected.** Use a public `https://` URL with no user or password in it. Internal hostnames and `localhost` are blocked on purpose.

**A YouTube link says "title only, no transcript."** That video has no captions, or YouTube refused the caption track. The draft still runs from the title. Use a watch, `youtu.be`, or shorts link to one video. After you pull a new version, stop the old `server.py` and start it again.

**The short post is missing.** The article is still shown. Run it again. A smaller model is more likely to skip the second section.

**The video button is missing.** ffmpeg is not on the PATH. Install it, reload the page, and write the draft again. The PDF, the images, and the article cover do not need ffmpeg. Play still previews the explainer.

**Plan the video asks for more lines.** The diagram needs a headline of at least three words and three sentences. Add another sentence on its own line.

**The cards look plain.** They are type, not a generated photograph. LinkedIn document posts that get read are large words on a steady layout. The first card is the hook. Upload the PDF, and LinkedIn adds the arrows and the page dots.

**The laptop fans stay loud.** That is the model running on the CPU or GPU. Close other large apps before using Mistral Small 3.2.

## Project layout

```
server.py           local web server and Ollama client
cards.py            card text from the draft, with a local-model pass in front of it
media.py            optional MP4 export through ffmpeg
motion.py           explainer storyboard from the draft, a script, or one card
documents.py        PDF, Word, and text attachment reading
youtube.py          YouTube transcript reading
tests/test_links.py link and transcript checks that do not call Ollama
tests/test_cards.py card text and video-frame checks
tests/test_motion.py explainer text and frame checks
tests/test_scenes.py card layouts, timing, and joining checks
static/index.html   the form
static/app.js       streaming, copy, and download
static/cards.js     card drawing, PDF, PNG zip, and the video request
static/motion.js    explainer drawing
static/script.js    animated video from one script per card
static/styles.css
start.sh            prerequisite checks, then python3 server.py
requirements.txt    no third-party packages
.github/workflows/python-app.yml  checks syntax and the tests on push to main
pytest.ini          lets those tests import the app
docs/               GitHub Pages: the animated deck, and docs/cards/ for the research note
```

## Security notes

- No API keys, tokens, or passwords are stored in this repo. Ollama on localhost does not need a key for these models. Card drawing and the PDF stay in the browser. The video endpoint only runs ffmpeg on files just drawn for that download, in a temporary folder that is deleted afterward. It does not take a key.
- The fetcher does not accept credentials inside a URL. YouTube transcripts are read without an API key and without browser cookies. A caption address from the player response is opened only after the same public-address check as any other link, and only when the host is YouTube or Google video.
- An attached file is read in memory and discarded. The original file is not written to disk. Only PDF, Word (`.doc`, `.docx`), and `.txt` contents are accepted, and only after the bytes match that type.
- Outbound page fetches use the operating system's TLS stack. This app does not ship certificates or its own cryptography.
- Do not paste customer data or other sensitive material into the form if that conflicts with the rules of the machine you are using. The prompt stays on the laptop, and so does the model, but the text is still processed by local software you installed.
