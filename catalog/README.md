# Plugin library catalog

`registry.json` is what **Browse the plugin library** in Mosaic Studio reads (from this repository's `main` branch, or from
the address in the `MOSAICVID_CATALOG` environment variable: a URL or a file path).

To publish a plugin:

1. Zip the plugin folder (the one with `plugin.json`) and put the zip somewhere downloadable, for example next to this file.
2. Get its checksum: `python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" my-plugin-1.0.0.zip`
3. Add an entry to `registry.json`:

```json
{"api": 1, "plugins": [
  {"id": "birthday", "name": "Birthday video", "version": "1.0.0", "author": "You",
   "description": "A personal film with names, a message and music.",
   "chips": ["Names + message", "Music"],
   "download": "birthday-1.0.0.zip",
   "sha256": "<checksum from step 2>"}
]}
```

`download` is a URL, or a path relative to `registry.json`. The app refuses a download whose checksum does not match.

The zip can live next to `registry.json` in this folder (as `birthday-1.0.0.zip` does, built from commit `03d9582` of
[mosaic-birthday-plugin](https://github.com/mahatosourav00/mosaic-birthday-plugin)); a new plugin version is a new zip, a new
`version` and a new checksum.
