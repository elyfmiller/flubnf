#!/usr/bin/env Rscript
# validate_submission.R: run a FluSight submission CSV through the hub's own
# acceptance code (hubValidations), exactly as the hub's CI would, without
# touching the hub clone's working tree.
#
# Usage:
#   Rscript scripts/validate_submission.R <submission.csv> <hub_clone_path> [--window]
#
#   <submission.csv>   a hubverse submission file named
#                      <reference_date>-<model_id>.csv (what the Output tab
#                      offers, or any file following that pattern)
#   <hub_clone_path>   a checkout of cdcepi/FluSight-forecast-hub (the public
#                      clone is enough; no private engine is needed)
#   --window           also run the submission window check (off by default:
#                      the content checks are what a rehearsal needs, and a
#                      past reference date always fails the window)
#
# What it does: creates a temporary git worktree of the hub so the clone is
# never dirtied, places the file at model-output/<model_id>/, copies the model
# metadata card from this repo's model-metadata/ when the hub does not carry
# it yet (a first submission PR carries both files), runs
# hubValidations::validate_submission, prints one unambiguous GREEN or RED
# line plus every failing check, and exits nonzero on RED.

lib_extra <- path.expand("~/Documents/FluBNF-local/rlib")
if (dir.exists(lib_extra)) .libPaths(c(lib_extra, .libPaths()))
ok <- suppressWarnings(suppressMessages(require(hubValidations, quietly = TRUE)))
if (!ok) {
  cat("RED: the hubValidations R package is not installed.\n")
  cat("Install it with: install.packages(\"hubValidations\",",
      "repos = c(\"https://hubverse-org.r-universe.dev\",",
      "\"https://cloud.r-project.org\"))\n")
  quit(status = 2)
}

args <- commandArgs(trailingOnly = TRUE)
flags <- args[startsWith(args, "--")]
args <- args[!startsWith(args, "--")]
if (length(args) != 2) {
  cat("usage: Rscript validate_submission.R <submission.csv> <hub_clone_path> [--window]\n")
  quit(status = 2)
}
sub_csv <- normalizePath(args[[1]], mustWork = FALSE)
hub <- normalizePath(args[[2]], mustWork = FALSE)
with_window <- "--window" %in% flags

if (!file.exists(sub_csv)) {
  cat("RED: submission file not found:", sub_csv, "\n")
  quit(status = 2)
}
if (!dir.exists(file.path(hub, "hub-config"))) {
  cat("RED: not a hub clone (no hub-config directory):", hub, "\n")
  quit(status = 2)
}

fname <- basename(sub_csv)
model_id <- sub("\\.csv$", "", sub("^\\d{4}\\-\\d{2}\\-\\d{2}\\-", "", fname))
if (identical(model_id, fname)) {
  cat("RED: file name does not look like <reference_date>-<model_id>.csv:",
      fname, "\n")
  quit(status = 2)
}

# a temporary worktree keeps the hub clone clean no matter what happens
wt <- file.path(tempdir(), paste0("hubwt_", Sys.getpid()))
rc <- system2("git", c("-C", shQuote(hub), "worktree", "add", "--detach",
                       shQuote(wt), "HEAD"), stdout = FALSE, stderr = FALSE)
if (rc != 0 || !dir.exists(wt)) {
  cat("RED: could not create a git worktree of the hub clone.\n")
  quit(status = 2)
}
# on.exit is unreliable at Rscript top level, so the body below runs inside
# a function and the worktree is removed explicitly before every exit
remove_worktree <- function() {
  system2("git", c("-C", shQuote(hub), "worktree", "remove", "--force",
                   shQuote(wt)), stdout = FALSE, stderr = FALSE)
}

run_validation <- function() {
dest_dir <- file.path(wt, "model-output", model_id)
dir.create(dest_dir, recursive = TRUE, showWarnings = FALSE)
file.copy(sub_csv, file.path(dest_dir, fname), overwrite = TRUE)

# the metadata card: the hub requires model-metadata/<model_id>.yml. A first
# submission PR adds it alongside the CSV; mirror that by copying this repo's
# card into the worktree when the hub does not have one yet.
meta_hub <- file.path(wt, "model-metadata", paste0(model_id, ".yml"))
if (!file.exists(meta_hub)) {
  script_path <- sub("^--file=", "",
                     grep("^--file=", commandArgs(FALSE), value = TRUE))
  candidates <- c(
    if (length(script_path))
      file.path(dirname(normalizePath(script_path)), "..", "model-metadata",
                paste0(model_id, ".yml")),
    file.path(dirname(sub_csv), paste0(model_id, ".yml")))
  found <- candidates[file.exists(candidates)]
  if (length(found)) {
    file.copy(found[[1]], meta_hub)
    cat("NOTE: metadata card was not in the hub yet; using",
        normalizePath(found[[1]]), "as a first submission PR would.\n")
  } else {
    cat("NOTE: no metadata card found for", model_id,
        "so the metadata check will fail.\n")
  }
}

rel <- file.path(model_id, fname)
v <- tryCatch(
  validate_submission(hub_path = wt, file_path = rel,
                      skip_submit_window_check = !with_window),
  error = function(e) e)
if (inherits(v, "error")) {
  cat("RED: hubValidations itself errored:", conditionMessage(v), "\n")
  return(1L)
}

n_checks <- 0L
bad <- character(0)
for (w in names(v)) {
  for (n in names(v[[w]])) {
    chk <- v[[w]][[n]]
    n_checks <- n_checks + 1L
    cls <- class(chk)[[1]]
    msg <- gsub("\n", " ", cli::ansi_strip(conditionMessage(chk)))
    verdict <- switch(cls,
                      check_success = "pass",
                      check_info = "info",
                      check_failure = "FAIL",
                      check_error = "FAIL",
                      check_exec_error = "FAIL",
                      cls)
    cat(sprintf("  [%s] %s: %s\n", verdict, n, msg))
    if (verdict == "FAIL") bad <- c(bad, sprintf("%s: %s", n, msg))
  }
}

if (length(bad) == 0) {
  cat(sprintf("GREEN: %s passed all %d hubValidations checks.\n",
              fname, n_checks))
  return(0L)
} else {
  cat(sprintf("RED: %s failed %d of %d hubValidations checks.\n",
              fname, length(bad), n_checks))
  for (b in bad) cat("  FAILING:", b, "\n")
  return(1L)
}
}

status <- tryCatch(run_validation(), error = function(e) {
  cat("RED: unexpected error:", conditionMessage(e), "\n")
  1L
})
remove_worktree()
quit(status = status)
