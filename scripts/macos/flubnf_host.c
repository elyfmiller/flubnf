/*
 * flubnf_host.c: FluBNF.app's in-bundle Python host (macOS).
 *
 * Built by scripts/macos/build_app_host.sh into
 *     FluBNF.app/Contents/MacOS/FluBNF         (gitignored, per machine)
 * and run as
 *     FluBNF <repo>/.venv/bin/flubnf window    (flubnf-launch, a Dock launch)
 *     FluBNF <repo>/.venv/bin/flubnf app       (FluBNF.command, in Terminal)
 *
 * WHY. The Dock names a window by the app bundle its process belongs to, and
 * macOS decides that bundle from the path of the running executable.
 *   - A framework Python (python.org, Homebrew): the venv's bin/python is a
 *     symlink to Python.framework/.../bin/python3.12, which is the
 *     Mac/Tools/pythonw.c stub. That stub sets __PYVENV_LAUNCHER__ and execs
 *     .../Resources/Python.app/Contents/MacOS/Python, so the window process
 *     belongs to Python.app: "Python" in the Dock, and Keep in Dock pins
 *     Python.app.
 *   - A non-framework Python (Anaconda, pyenv, uv): the process is an
 *     unbundled binary, which the Dock labels by its file name, "python3.12".
 * Editing NSBundle.mainBundle().infoDictionary() at runtime changes neither.
 * This host instead embeds the libpython the venv was made from, so the
 * executable that owns the window lives in FluBNF.app. Its main bundle, Dock
 * name, icon and Keep in Dock target are then FluBNF's.
 *
 * BEHAVIOUR.  FluBNF [args...]  runs as  <repo>/.venv/bin/python [args...]
 * argv[0] handed to Python is the venv's python. CPython's getpath (3.11+)
 * takes program_name from argv[0] and sets executable = abspath(argv[0]);
 * on macOS it also sets real_executable to that value. It then reads
 * pyvenv.cfg next to it. So sys.executable, sys.prefix and site-packages
 * are the venv's, exactly as when .venv/bin/python runs. Children started
 * with sys.executable (subprocess) run the venv's python, never this host.
 * The process's own command line (what ps, pgrep and the pidfile takeover
 * read) stays the exec'd one:
 *     .../FluBNF.app/Contents/MacOS/FluBNF .../.venv/bin/flubnf window
 *
 * <repo> comes from this binary's own path
 * (<repo>/<Name>.app/Contents/MacOS/<exe>), so a moved or renamed clone keeps
 * working. The build bakes in nothing except the libpython it links.
 *
 * STARTUP FAILURE (FLUBNF_HOST_FALLBACK non-empty, which only flubnf-launch
 * sets). Two cases are caught here, before Python starts: no venv, and a
 * venv of another Python minor version. For each, this host reopens
 * FluBNF.command in Terminal, where setup and errors are visible.
 * Failures inside Python go to scripts/macos/host_boot.py, which runs the
 * script. A C check after Py_BytesMain would miss most of them: an uncaught
 * SystemExit(n) from a script ends in Py_Exit() -> exit()
 * (Python/pythonrun.c, handle_system_exit), so Py_BytesMain never returns.
 * The flag is removed from the environment, so no child inherits it. The
 * fallback cannot loop: FluBNF.command never sets the flag.
 *
 * The file also compiles on Linux (it reads /proc/self/exe there) so the
 * tests can build and run it. Only macOS gives it a purpose.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

#define TAG "flubnf-host: "

/* This executable's resolved path. 0 on success. */
static int self_path(char out[PATH_MAX])
{
#ifdef __APPLE__
    char raw[PATH_MAX * 2];
    uint32_t size = sizeof raw;
    if (_NSGetExecutablePath(raw, &size) != 0)
        return -1;
    return realpath(raw, out) ? 0 : -1;
#else
    return realpath("/proc/self/exe", out) ? 0 : -1;
#endif
}

/* Cut the last path component off `p` in place; returns it, or NULL. */
static const char *pop(char *p)
{
    char *s = strrchr(p, '/');
    if (s == NULL || s == p)
        return NULL;
    *s = '\0';
    return s + 1;
}

static int ends_with(const char *s, const char *suffix)
{
    size_t n = strlen(s), m = strlen(suffix);
    return n >= m && strcmp(s + n - m, suffix) == 0;
}

/* <repo> from <repo>/<Name>.app/Contents/MacOS/<exe>; 0 on success. The
 * layout is checked, not assumed, so a copy elsewhere refuses to guess. */
static int bundle_repo(const char *exe, char repo[PATH_MAX])
{
    const char *name;
    if (strlen(exe) >= PATH_MAX)
        return -1;
    strcpy(repo, exe);
    if (pop(repo) == NULL)                                   /* the exe */
        return -1;
    if ((name = pop(repo)) == NULL || strcmp(name, "MacOS") != 0)
        return -1;
    if ((name = pop(repo)) == NULL || strcmp(name, "Contents") != 0)
        return -1;
    if ((name = pop(repo)) == NULL || !ends_with(name, ".app"))
        return -1;
    return 0;
}

/* 1 when pyvenv.cfg names this host's Python major.minor (or names none),
 * 0 on a mismatch. Keys seen in the wild: "version" (venv), "version_info"
 * (uv, virtualenv). */
static int venv_version_ok(const char *cfg)
{
    FILE *f = fopen(cfg, "r");
    char line[512];
    int ok = 1;
    if (f == NULL)
        return 1;
    while (fgets(line, sizeof line, f)) {
        const char *p = line;
        const char *eq;
        int major = 0, minor = 0;
        while (*p == ' ' || *p == '\t')
            p++;
        if (strncmp(p, "version", 7) != 0)
            continue;
        if ((eq = strchr(p, '=')) == NULL)
            continue;
        if (sscanf(eq + 1, " %d.%d", &major, &minor) == 2) {
            ok = (major == PY_MAJOR_VERSION && minor == PY_MINOR_VERSION);
            break;
        }
    }
    fclose(f);
    return ok;
}

/* Hand the launch to Terminal (FluBNF.command) so the user sees why. Only
 * returns if that could not be started. */
static void to_terminal(const char *repo, const char *why)
{
    char cmd[PATH_MAX + 32];
    fprintf(stderr, TAG "%s; reopening FluBNF.command in Terminal\n", why);
    fflush(stderr);
    if (snprintf(cmd, sizeof cmd, "%s/FluBNF.command", repo) >= (int)sizeof cmd)
        return;
#ifdef __APPLE__
    execl("/usr/bin/open", "open", "-a", "Terminal", cmd, (char *)NULL);
    perror(TAG "open");
#else
    (void)cmd;
#endif
}

static int join(char out[PATH_MAX], const char *repo, const char *rel)
{
    return snprintf(out, PATH_MAX, "%s/%s", repo, rel) < PATH_MAX ? 0 : -1;
}

int main(int argc, char **argv)
{
    char exe[PATH_MAX], repo[PATH_MAX], py[PATH_MAX], cfg[PATH_MAX],
         boot[PATH_MAX], why[128];
    const char *fb = getenv("FLUBNF_HOST_FALLBACK");
    int fallback = fb != NULL && *fb != '\0';
    char **pargv;
    int pargc = 0, i;

    /* Children must not inherit the flag. An inherited launcher variable
     * would point getpath at some other interpreter or venv. */
    unsetenv("FLUBNF_HOST_FALLBACK");
    unsetenv("__PYVENV_LAUNCHER__");
    unsetenv("PYTHONEXECUTABLE");
    unsetenv("PYTHONHOME");

    if (self_path(exe) != 0 || bundle_repo(exe, repo) != 0) {
        fprintf(stderr, TAG "cannot place myself inside <repo>/<Name>.app/"
                        "Contents/MacOS (%s)\n", argv[0]);
        return 70;
    }
    if (join(py, repo, ".venv/bin/python") || join(cfg, repo, ".venv/pyvenv.cfg")
        || join(boot, repo, "scripts/macos/host_boot.py")) {
        fprintf(stderr, TAG "path too long: %s\n", repo);
        return 70;
    }
    if (access(py, X_OK) != 0 || access(cfg, R_OK) != 0) {
        if (fallback)
            to_terminal(repo, "no .venv yet (first run, or setup did not finish)");
        fprintf(stderr, TAG "%s is missing\n", py);
        return 69;
    }
    if (!venv_version_ok(cfg)) {
        snprintf(why, sizeof why, ".venv is not a Python %d.%d venv; this host "
                 "needs rebuilding", PY_MAJOR_VERSION, PY_MINOR_VERSION);
        if (fallback)
            to_terminal(repo, why);
        fprintf(stderr, TAG "%s\n", why);
        return 69;
    }

    pargv = calloc((size_t)argc + 2, sizeof *pargv);
    if (pargv == NULL)
        return 71;
    pargv[pargc++] = py;               /* argv[0]: getpath finds the venv here */
    /* A script launch from the Dock runs under host_boot.py, which reopens
     * Terminal when the script fails at startup. */
    if (fallback && argc > 1 && argv[1][0] != '-' && access(boot, R_OK) == 0)
        pargv[pargc++] = boot;
    for (i = 1; i < argc; i++)
        pargv[pargc++] = argv[i];
    pargv[pargc] = NULL;
    return Py_BytesMain(pargc, pargv);
}
