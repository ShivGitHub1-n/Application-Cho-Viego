# Application data directory

## Path policy

Application Viego stores user-owned SQLite state outside the Git repository.
On Windows the default is:

`%LOCALAPPDATA%\Application Viego`

If `LOCALAPPDATA` is unavailable, the fallback is
`%USERPROFILE%\AppData\Local\Application Viego`. Non-Windows development uses
`$XDG_DATA_HOME/application-viego` or `~/.local/share/application-viego`.

Set `APPLICATION_VIEGO_DATA_DIR` to an absolute or relative directory for
portable runs and deterministic tests. The legacy `APP_DATA_DIRECTORY` setting
name remains readable, but the new environment variable is canonical. Tests
inject temporary directories and never rely on a checkout-local database.
Path construction occurs during dependency creation, not module import.

The profile store and Job Search state use the configured directory and the
configured SQLite filename. As a result, a saved profile such as
`shiv-arora-master-v1`, discovery runs, recommendations, and saved-job snapshots
remain available across branches, clones, and worktrees that use the same
application data directory.

## Compatibility import

When dependency construction can identify a repository root, it may inspect
only `<repository>/data/<configured database filename>`. If that database
exists and differs from the canonical database, the adapter imports rows from
an allowlist of known application tables with insert-if-absent behavior.
Existing canonical rows win. The process does not copy arbitrary repository
files, overwrite canonical records, import source configuration, or store
credentials with profiles.

Job provider registry files remain explicit configuration, not user state. A
missing or empty registry is reported by Job Search as no approved sources
configured. Merely opening the application or another page does not initialize
or call a job source.

The current Job Discovery contract persists confirmed preferences, discovered
jobs, runs, recommendations, and saved immutable snapshots. It has no
dismissed-job or applied-job lifecycle model; those states therefore were not
silently relocated or simulated as part of this persistence fix.
