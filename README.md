# Sen Lab Protein Sequence Analysis Suite

Protein-GUI is a PyQt5 desktop application for sequence search, clustering, alignment, motif inspection, and database management. The app now supports an app-managed tool runtime so most users can install required command-line tools from inside the GUI instead of configuring PATHs by hand.

## Main Workflows

- `Protein Search`: unified protein search page with BLASTP or MMseqs2 selection
- `BLASTN`: nucleotide search against remote NCBI databases or local BLAST databases
- `Clustering`: MMseqs2 clustering from FASTA input or selected search results
- `Alignment`: Clustal Omega multiple sequence alignment with export support
- `Motif Search`: glycosylation motif analysis and result visualization
- `Tools`: install and manage BLAST+, MMseqs2, blastdbcmd, and Clustal Omega
- `Databases`: download and manage sequence databases for BLAST and MMseqs2

## Default Setup

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

2. Launch the app:

```bash
python protein_gui.py
```

3. Install tools from inside the GUI when needed:
- Open the `Tools` tab in the main navigation bar and install or repair tools there.
- Or start a feature such as Protein Search, BLASTN, Alignment, or Clustering and accept the just-in-time install prompt.

For most users, this is now the recommended setup path. You should not need to manually install `blastp`, `blastn`, `mmseqs`, `blastdbcmd`, or `clustalo` first on supported platforms.

## Managed Runtime

The managed runtime uses a private micromamba environment owned by the app.

- Managed tools live in a per-user tools directory.
- Tool resolution is handled centrally by `core/tool_runtime.py`.
- The runtime can prefer `managed`, `configured`, `system`, or `wsl` sources.
- Tool status is surfaced in the GUI and persisted in a lightweight tool-state store.

### Tools tab

The `Tools` tab in the main window lists each external dependency as a card.

Each tool card shows:
- current availability
- current source (`managed`, `system`, `configured`, or `wsl`)
- detected version
- executable path when available

Each tool card supports:
- managed install or repair, when the platform supports it
- switching source preference
- refreshing detection status

## Platform Behavior

### macOS and Linux

- Managed native installs are the preferred path.
- The Tools tab and JIT prompts can install supported tools into the app-managed environment.
- You can still use configured or system tools if you prefer.

### Windows

- Windows currently relies on `WSL` or system-backed tool execution for these bioinformatics tools.
- The GUI still exposes tool status and source selection, but managed micromamba installs are not the primary path on Windows right now.
- Windows users should make sure WSL is installed and that required tools are available there when applicable.

## Feature-to-Tool Mapping

- `Protein Search` with BLASTP requires `BLAST+`
- `Protein Search` with MMseqs2 requires `MMseqs2`
- MMseqs2 protein searches that need BLAST database conversion also require `blastdbcmd`
- `BLASTN` requires `BLAST+`
- `Alignment` requires `Clustal Omega`
- `Clustering` requires `MMseqs2`

## Databases vs Tools

Tools and databases are managed separately.

- Tools are executables such as `blastp`, `blastn`, `mmseqs`, `blastdbcmd`, and `clustalo`.
- Tools can be installed through the managed runtime on supported platforms.
- Databases are search datasets stored outside the managed runtime.
- Local BLAST databases live under `blast_databases/` by default.
- Local MMseqs2 databases live under `mmseqs_databases/` by default.

Installing a tool does not download search databases for you. Database downloads and installs are handled from the `Databases` page.

## Results and Navigation

- Protein and nucleotide search results are shown in native Qt result panels rather than raw HTML-only views.
- Search results can be exported.
- Protein search results can flow directly into clustering or alignment.
- Alignment, clustering, and other analysis pages use resizable layouts so users can inspect outputs in larger panes.

## Advanced Configuration

Advanced users can still control resolution behavior through `config.json`.

Relevant settings include:
- `preferred_tool_sources`
- `tool_source_overrides`
- `managed_tools_root`
- `managed_env_name`
- explicit configured paths such as `blast_path`, `mmseqs_path`, `clustalo_path`, and `blastdbcmd_path`

`setup_wizard.py` is now a diagnostics tool. It reports what the runtime sees, but it does not rewrite `config.json` as part of normal use.

## Diagnostics

Run the diagnostics tool if you want a terminal-readable snapshot of the current runtime state:

```bash
python setup_wizard.py
```

Optional pause for double-click launches:

```bash
python setup_wizard.py --pause
```

## Troubleshooting

### A tool says missing

- Open the `Tools` tab and inspect the tool card.
- If managed installs are supported on your platform, use `Install` or `Repair Managed Install`.
- If you are on Windows, verify the tool is available in WSL/system tooling instead.

### A feature prompts for install every time

- Refresh the relevant tool card in the `Tools` tab.
- Check whether a source override is forcing the app to use `system` or `wsl` instead of `managed`.
- Re-run the feature after install to confirm the post-install source is the one you expect.

### MMseqs2 cannot search a BLAST database

- MMseqs2 uses its own database format.
- The app can prompt to convert compatible BLAST databases when `blastdbcmd` and `mmseqs` are available.

### BLASTN remote searches are slow

- Remote BLASTN is inherently slower than local searches.
- Prefer smaller remote databases when possible.
- For repeated work, install local nucleotide databases and run BLASTN locally.

### Managed install fails

- Retry from the Tools tab.
- Check network availability.
- Re-run `python setup_wizard.py` to inspect the runtime state.
- If needed, remove or repair the managed tools directory configured by `managed_tools_root`.

### Windows setup is confusing

- Start by confirming `wsl --status` works.
- Install the required bioinformatics tools inside WSL if the Tools tab reports they are missing.
- Use the diagnostics tool to compare what the terminal sees with what the GUI shows.

## Project Structure

- `protein_gui.py`: app entry point, main window, tab navigation, theme toggle
- `ui/`: feature pages, dialogs, widgets, and theming
- `core/`: workers, runtime resolution, micromamba management, config, and database logic
- `utils/`: parsing, export, and helper utilities
- `tests/`: focused regression coverage for runtime and worker behavior

Proprietary - Sen Lab
