# LinkedIn drafts

A local writing desk for LinkedIn. It runs on your laptop, calls [Ollama](https://ollama.com) on `127.0.0.1`, and does not send the draft to a cloud model.

You give it a company name (optional), one or more topics, up to five links (optional), and one PDF, Word, or text file (optional). A YouTube link can include its transcript. It writes two plain-text pieces you can paste into LinkedIn:

- a longer article
- a shorter feed post

There is no database. Drafts are not saved on the server. Copy or download them from the page.

## What you need

| Requirement | Notes |
| --- | --- |
| Laptop | macOS, Linux, or Windows. The checked-in start script is for macOS and Linux. |
| Memory | 16 GB is enough for Gemma 4 12B. Mistral Small 3.2 is a 15 GB model and is comfortable on 24 GB. On a 16 GB machine it will be slow or fail to load. |
| Free disk | About 8 GB for Gemma, about 15 GB for Mistral, plus a few GB of overhead. Pull both only if you have about 30 GB free. |
| Python | 3.10 or newer. The app uses the standard library only. |
| Ollama | 0.31.0 or newer. Gemma 4 12B refuses to load on older releases. |
| Network, once | `ollama pull` downloads the model weights. After that, generation stays on this machine. Fetching a link you paste also uses the network, from this app, not from a cloud LLM. |

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

## Use the form

1. Choose **Mistral Small 3.2** or **Gemma 4 12B**.
2. Company name is optional. Example: `Cisco`. The model may mention that name. It is instructed not to invent products, announcements, or metrics.
3. Topics are required. Separate them with commas or new lines. Example: `cybersecurity, agentic ops`. Up to 12 topics.
4. Links are optional, one per line, up to five. A normal web page or blog post is fetched and trimmed to text. A YouTube link includes the transcript when YouTube provides captions. English is preferred, then any other language. A Vimeo link contributes the video title and author only.
5. A reference file is optional. Choose one `.pdf`, `.doc`, `.docx`, or `.txt` file, up to 8 MB. Its text is read on this laptop and used with the links. The file is not saved. A scanned PDF with no text layer cannot be read.
6. Click **Write drafts**. The first reply after a cold start is slower because Ollama loads the model into memory.
7. Copy or download the article (`linkedin-article.txt`) and the short post (`linkedin-post.txt`).

Paste the text into LinkedIn yourself. This app does not log in to LinkedIn and does not publish.

## How a request works

1. The browser posts the form to `POST /api/generate` on this laptop.
2. Each link is checked before it is opened. Only `http` and `https` are allowed. Links with a username or password are rejected. Loopback, private, link-local, and other non-public addresses are rejected.
3. Page text is extracted locally and capped so the prompt stays bounded. A YouTube link is handled separately: the app asks YouTube's player endpoint for a caption track and downloads that track. The caption address is opened only when its host is YouTube or Google video. If a file was attached, its text is extracted in memory the same way and added as another source. PDF, Word, and text files are parsed as data. They are not opened in an editor and not saved.
4. The prompt is sent to Ollama's chat API. Gemma's thinking mode is turned off so the reply is the draft, not a reasoning trace.
5. The reply is split into the article and the short post and streamed back to the page.

`GET /api/health` reports whether Ollama is up and which of the two models are installed. The page calls that when it loads.

## Limits

- Five links, each read is capped at about 500 KB and 12 seconds.
- About 4,000 characters of text are kept from each page.
- About 8,000 characters of each YouTube transcript are kept. Videos without captions, and Vimeo links, contribute the title only.
- One attachment, up to 8 MB. About 8,000 characters of its text are kept. Encrypted PDFs, and scans without a text layer, are rejected.
- Topics and the company field are length-capped.
- The model can still be vague or wrong. Read the draft before you post it. If you did not supply a source, the model is writing from the topic names only.
- A YouTube video with no captions, or a transcript YouTube refuses to serve, is used as a title only. The draft still runs.
- Generation time depends on the laptop. Gemma on an Apple Silicon machine with the model already loaded often finishes in under a minute. Mistral Small 3.2 takes longer and uses most of a 24 GB machine while it runs.

## Troubleshooting

**The page says Ollama is not running.** Open the Ollama app, or run `ollama serve`, then reload [http://127.0.0.1:8765](http://127.0.0.1:8765).

**A model is greyed out.** It is not in `ollama list`. Pull it with the command in the table above.

**`gemma4:12b` fails to load.** Upgrade Ollama to 0.31.0 or newer (`ollama --version`), then pull the model again.

**Port 8765 is already in use.** Stop the other copy of `server.py`, or change `PORT` in `server.py` and open that port instead.

**A link is rejected.** Use a public `https://` URL with no user or password in it. Internal hostnames and `localhost` are blocked on purpose.

**The short post is missing.** The article is still shown. Run it again. A smaller model is more likely to skip the second section.

**The laptop fans stay loud.** That is the model running on the CPU or GPU. Close other large apps before using Mistral Small 3.2.

## Project layout

```
server.py           local web server and Ollama client
documents.py        PDF, Word, and text attachment reading
youtube.py          YouTube transcript reading
static/index.html   the form
static/app.js       streaming, copy, and download
static/styles.css
start.sh            prerequisite checks, then python3 server.py
requirements.txt    no third-party packages
```

## Security notes

- No API keys, tokens, or passwords are stored in this repo. Ollama on localhost does not need a key for these models.
- The fetcher does not accept credentials inside a URL. YouTube transcripts are read without an API key and without browser cookies. A caption address from the player response is opened only after the same public-address check as any other link, and only when the host is YouTube or Google video.
- An attached file is read in memory and discarded. The original file is not written to disk. Only PDF, Word (`.doc`, `.docx`), and `.txt` contents are accepted, and only after the bytes match that type.
- Outbound page fetches use the operating system's TLS stack. This app does not ship certificates or its own cryptography.
- Do not paste customer data or other sensitive material into the form if that conflicts with the rules of the machine you are using. The prompt stays on the laptop, and so does the model, but the text is still processed by local software you installed.
