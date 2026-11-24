# Setup and Recovery

## Prerequisites

- Python 3.11+
- Git with HTTPS credentials
- GitHub CLI authenticated: `gh auth status`
- OpenCode installed and authenticated for supervisor workers
- Qt 6.4+ and CMake 3.21+ for local Qt builds

## Clone and test

```sh
git clone https://github.com/DevTunaSoft/Canopy.git
cd Canopy
git fetch origin
python -m unittest discover -s tests -v
```

On Windows, three POSIX-only test modules may skip; Ubuntu CI is authoritative.

## Supervisor

State root is outside the repository by default. Do not commit state.

```powershell
py -3 tools/canopy_supervisor.py --state-root C:\CanopySupervisor\state init --repo C:\path\to\Canopy
py -3 tools/canopy_supervisor.py --state-root C:\CanopySupervisor\state check
py -3 tools/canopy_supervisor.py --state-root C:\CanopySupervisor\state run
```

Status:

```powershell
py -3 tools/canopy_supervisor.py --state-root C:\CanopySupervisor\state status
```

Stop cleanly:

```powershell
py -3 tools/canopy_supervisor.py --state-root C:\CanopySupervisor\state stop
```

Recovery:

```powershell
py -3 tools/canopy_supervisor.py --state-root C:\CanopySupervisor\state recover
py -3 tools/canopy_supervisor.py --state-root C:\CanopySupervisor\state run
```

## Qt

```sh
cmake -S prototype/classic -B build/classic -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/classic --parallel 2
./build/classic/canopy-classic-spike
```

CI installs Qt and captures screenshots. Local builds require Qt 6.4+.

## Approved artwork

Use the exact user-supplied ZIP:

```sh
python tools/install_approved_art_zip.py --archive /path/to/Canopy_Classic_Exact_Artwork_Runtime.zip --destination prototype/classic/assets/approved
```

Do not extract, recolor, crop, or substitute assets.

## Mint VM

The existing `Canopy-Test-Mint` VM is powered off and has no Guest
Additions or SSH key. Do not delete or replace it. Guest acceptance remains
blocked until those prerequisites are configured.
