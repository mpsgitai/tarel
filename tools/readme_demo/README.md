# Record the README demo

The **Record README demo** GitHub Actions workflow records the real TAREL GUI with a small,
synthetic sales graph. It switches from Structure (Space) to Lineage and back without changing
the application's animation or layout code. No external database or LLM is called.

The workflow runs for pull requests that change this directory or its workflow. Once merged,
it can also be started from **Actions → Record README demo → Run workflow** on GitHub's website.

Download the `tarel-space-lineage-demo` artifact from the completed run. It contains the GIF,
the original video, two screenshots, and diagnostics. Review the result before placing
`space-to-lineage.gif` in `docs/assets/` and embedding it under **Explore through Space and Lineage**.
The workflow only uploads artifacts; it does not push commits or modify the README.

For an independently configured local development machine:

```bash
python -m pip install -e . 'playwright==1.56.0'
python -m playwright install --with-deps chromium
# Install ffmpeg using the OS package manager.
python tools/readme_demo/record.py --output .tarel/readme-recording
```

The recording uses a temporary state root, port 8765, a 1440×900 viewport and original animation
speed. The GIF is reduced to 1120 pixels wide at 20 fps. Generated relationships remain labelled
as synthetic drafts; this is a navigation demonstration, not a lineage accuracy benchmark.
