from tokenscope.projects import Folder

WS = "c:/Users/me/Desktop"
CFG = {"workspace_roots": [WS, "c:/Users/me/code"], "project_aliases": {}}


def test_subdirectories_fold_to_the_project():
    f = Folder(CFG)
    assert f.fold(f"{WS}/myapp") == f"{WS}/myapp"
    assert f.fold(f"{WS}/myapp/backend") == f"{WS}/myapp"
    assert f.fold(f"{WS}/myapp/frontend/src/i18n") == f"{WS}/myapp"
    assert f.fold(f"{WS}\\myapp\\backend") == f"{WS}/myapp"


def test_sibling_projects_stay_apart():
    f = Folder(CFG)
    assert f.fold(f"{WS}/myapp") != f.fold(f"{WS}/otherapp")


def test_path_outside_every_root_keeps_its_own_identity():
    f = Folder(CFG)
    # A home-directory session must not swallow every project under it.
    assert f.fold("c:/Users/me") == "c:/Users/me"
    assert f.fold("d:/scratch/thing/sub") == "d:/scratch/thing/sub"


def test_workspace_root_itself_is_its_own_project():
    f = Folder(CFG)
    assert f.fold(WS) == WS


def test_longest_root_wins():
    f = Folder({"workspace_roots": ["c:/Users/me/OneDrive", "c:/Users/me/OneDrive/Desktop"]})
    assert f.fold("c:/Users/me/OneDrive/Desktop/app/backend") == "c:/Users/me/OneDrive/Desktop/app"


def test_alias_merges_a_renamed_folder():
    f = Folder({**CFG, "project_aliases": {f"{WS}/old name": f"{WS}/new name"}})
    assert f.fold(f"{WS}/old name") == f"{WS}/new name"
    assert f.fold(f"{WS}/old name/backend") == f"{WS}/new name"


def test_alias_on_a_raw_cwd_beats_the_workspace_rule():
    f = Folder({**CFG, "project_aliases": {f"{WS}/mono/pkg-a": f"{WS}/pkg-a"}})
    assert f.fold(f"{WS}/mono/pkg-a") == f"{WS}/pkg-a"
    assert f.fold(f"{WS}/mono/pkg-b") == f"{WS}/mono"


def test_case_variants_of_a_root_converge_on_the_configured_spelling():
    f = Folder(CFG)
    # Windows paths are case-insensitive, so the two spellings are one project.
    assert f.fold("c:/users/me/desktop/myapp/backend") == f"{WS}/myapp"
    assert f.fold(f"{WS}/myapp/frontend") == f"{WS}/myapp"


def test_no_roots_configured_is_the_old_per_cwd_behaviour():
    f = Folder({"workspace_roots": [], "project_aliases": {}})
    assert f.fold(f"{WS}/myapp/backend") == f"{WS}/myapp/backend"
