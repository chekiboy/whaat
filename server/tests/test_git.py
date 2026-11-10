import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from whaat.git import GitCommitter


def test_committers_sharing_a_folder_commit_every_file_when_they_run_at_once(tmp_path: Path) -> None:
    folder = tmp_path / "identity"
    folder.mkdir()
    GitCommitter().init(folder)
    for git_config in (["user.name", "probe"], ["user.email", "probe@example.invalid"]):
        subprocess.run(["git", "-C", str(folder), "config", *git_config], check=True)
    committers = [GitCommitter(), GitCommitter()]  # the memory and the journal each hold their own

    def save(i: int) -> str:
        path = folder / f"note_{i:02d}.md"
        path.write_text(f"note {i}\n")
        return committers[i % 2].commit(folder, [path], f"note {i}")

    with ThreadPoolExecutor(16) as pool:
        list(pool.map(save, range(40)))

    log = subprocess.run(["git", "-C", str(folder), "rev-list", "--count", "HEAD"], capture_output=True, text=True)
    status = subprocess.run(["git", "-C", str(folder), "status", "--porcelain"], capture_output=True, text=True)
    assert (log.stdout.strip(), status.stdout) == ("40", "")
