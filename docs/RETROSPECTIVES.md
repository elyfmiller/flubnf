# Retrospectives: archived runs, export and import

A retrospective replays a past season week by week on the data each
Saturday had (Retrospective tab, or `flubnf retro <season>`), then scores
every week against settled truth. Each season's replay lives under
`app/state/retro/<season>/`: `run_meta.json` (the run record), `scores.json`,
`weeks/<as-of>/quantiles.json` and `samples.json` per completed week, a
`playback_cache/` for the player and, once downloaded, the season report
HTML. The cache and the report are rebuilt on demand.

## Archived runs

Starting a fresh replay over a season with results offers to archive the
current tree: it is moved aside to `<season>__archived_<UTC stamp>/`, a
frozen sibling. Archived runs are listed under their season on the
Retrospective tab and on the Storage tab, open as
`/retro/<season>?archive=<stamp>` with the player and the report, and are
deleted from either tab. They are never resumed.

## Export and import of a replay

A replayed season can be viewed on another machine: the season page's
**Export replay** button (live and archived runs alike) writes one zip
bundle, `<season>-FluBNF-replay-<stamp>.flubnf-replay.zip`, under
`app/state/exports/` and downloads it. The bundle holds `manifest.json`
plus the run record, `scores.json` and every completed week's quantiles
and samples; the playback cache and the report stay behind, since the
importing machine rebuilds them. The manifest records the season, the
export stamp, the weeks, when and from which machine it was exported, the
FluBNF build, and a sha256 and size per file. A 26-week season of all 52
jurisdictions is about 10 MB.

**Import a replay** on the Retrospective tab (Settings card) takes the
file, or its path when it is already on this machine. The import lands as a
read-only archived entry of its season,
`<season>__archived_<export stamp>/`, with an `imported.json` marker, and is
labelled "imported from <host> on <date>" wherever archived runs are listed.
It never touches the live season tree, so a replay running here is
unaffected. Importing the same export twice is refused unless replaced.
Every member is checked against the manifest as it is extracted; a damaged
or altered bundle, a path outside it, a foreign format or an oversized
member is refused with one sentence and nothing lands.

The importing machine needs the hub clone for the player's truth and
baseline. The exported scores show as they are; when this app's scoring
rule is newer than the bundle's, or the hub's truth is newer, the season
page rescores the imported tree in the background as it does for any
archived run.

From the command line:

    flubnf retro export 2025-26 [--archive <stamp>] [--out DIR]
    flubnf retro import <FILE>.flubnf-replay.zip [--replace]

`flubnf retro <season>` still starts a replay; `export` and `import` are
its subcommands (`--root` points either at another retro root).
