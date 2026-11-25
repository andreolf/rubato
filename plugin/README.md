# Rubato plugin for Claude

Speed up videos dynamically: slow for the takeaways, fast through filler and silence. Nothing is cut and voices keep their pitch.

This plugin adds:

- the **Rubato connector**, a hosted MCP server at `https://www.tryrubato.com/mcp` with two tools, `speed_up_video` and `get_result`;
- a **skill** that tells Claude when and how to use it.

It contains no code that runs on your machine.

## Use

Give Claude a direct link to a recording and ask, for example: "Speed up this talk with Rubato: https://example.com/talk.mp4". Claude replies with the new length, the time saved, the passages that were kept slow or sped up, and a download link.

Limits: a direct public link to a media file, up to 15 minutes and 500 MB. Guide: https://www.tryrubato.com/connector

## What data it sends

The link you provide and the speed settings are sent to `www.tryrubato.com`. The server downloads the file at that link, transcribes it and re-times it. The source file is deleted when processing ends; the result is deleted after 30 minutes. There are no accounts, cookies or trackers. Nothing from your conversation is sent other than those tool inputs.

Privacy policy: https://www.tryrubato.com/privacy

## Longer files, local files, no upload

The open-source command-line tool, local MCP server and full skill run on your own machine with no length limit: https://github.com/andreolf/rubato

## Support

https://github.com/andreolf/rubato/issues

## License

MIT
