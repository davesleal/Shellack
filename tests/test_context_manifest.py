from tools.context_manifest import read_manifest, append_learned, build_manifest


def test_build_and_read(tmp_path):
    build_manifest(str(tmp_path), "TestApp", "src/app.ts\nsrc/lib.ts")
    result = read_manifest(str(tmp_path))
    assert "TestApp" in result
    assert "app.ts" in result


def test_append_learned(tmp_path):
    build_manifest(str(tmp_path), "TestApp", "")
    append_learned(str(tmp_path), "DECIDED: Use Supabase for auth")
    result = read_manifest(str(tmp_path))
    assert "Supabase" in result


def test_append_preserves_existing(tmp_path):
    build_manifest(str(tmp_path), "TestApp", "")
    append_learned(str(tmp_path), "FACT: 20 tables")
    build_manifest(str(tmp_path), "TestApp", "new structure")
    result = read_manifest(str(tmp_path))
    assert "20 tables" in result  # preserved across rebuild


def test_read_missing(tmp_path):
    assert read_manifest(str(tmp_path)) is None
