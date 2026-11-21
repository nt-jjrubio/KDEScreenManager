# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests del script auxiliar de KDEScreenManager (sin tocar las pantallas)."""

import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "package" / "contents" / "code" / "kdescreenmanager-helper.py"
FIXTURE = ROOT / "tests" / "fixtures" / "three-monitors.json"

spec = importlib.util.spec_from_file_location("ksm_helper", HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def load_fixture():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def run_cli(*argv, env=None):
    out = io.StringIO()
    with mock.patch.dict(os.environ, env or {}), redirect_stdout(out):
        code = helper.main(list(argv))
    return code, json.loads(out.getvalue())


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.layout_dir = Path(self.tmp.name) / "layouts"
        self.cfg = load_fixture()
        self.outputs = helper.connected_outputs(self.cfg)
        self.by_name = {o["name"]: o for o in self.outputs}
        # Sesión fija por defecto para que los tests no dependan del entorno.
        self.env = mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "x11"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def session_dir(self, session="x11"):
        return self.layout_dir / session

    def write_cfg(self, cfg):
        path = Path(self.tmp.name) / "cfg.json"
        path.write_text(json.dumps(cfg))
        return str(path)


class SingleTests(BaseCase):
    def test_single_dp2_keeps_mode_and_disables_others(self):
        layout = helper.snapshot(self.outputs)
        args = helper.build_single_args(self.outputs, "DP-2", layout)
        dp2_mode = self.by_name["DP-2"]["currentModeId"]
        self.assertEqual(args[:5], [
            "output.DP-2.enable",
            f"output.DP-2.mode.{dp2_mode}",
            "output.DP-2.rotation.none",
            "output.DP-2.position.0,0",
            "output.DP-2.priority.1",
        ])
        self.assertIn("output.DP-1.disable", args)
        self.assertIn("output.HDMI-A-2.disable", args)
        self.assertNotIn("output.DP-2.disable", args)

    def test_single_rotated_monitor_keeps_rotation(self):
        layout = helper.snapshot(self.outputs)
        args = helper.build_single_args(self.outputs, "HDMI-A-2", layout)
        self.assertIn("output.HDMI-A-2.rotation.right", args)

    def test_single_unknown_output_fails(self):
        with self.assertRaises(helper.HelperError):
            helper.build_single_args(self.outputs, "VGA-9", None)

    def test_single_disabled_output_uses_saved_mode(self):
        layout = helper.snapshot(self.outputs)
        cfg = copy.deepcopy(self.cfg)
        for o in cfg["outputs"]:
            if o["name"] != "DP-1":
                o["enabled"] = False
        outs = helper.connected_outputs(cfg)
        args = helper.build_single_args(outs, "HDMI-A-2", layout)
        hdmi_mode = self.by_name["HDMI-A-2"]["currentModeId"]
        self.assertIn(f"output.HDMI-A-2.mode.{hdmi_mode}", args)
        self.assertIn("output.HDMI-A-2.rotation.right", args)


class ExtendTests(BaseCase):
    def test_extend_restores_saved_layout_exactly(self):
        layout = helper.snapshot(self.outputs)
        # Estado "solo DP-1": el resto apagados y DP-1 movido a 0,0.
        cfg = copy.deepcopy(self.cfg)
        for o in cfg["outputs"]:
            if o["name"] == "DP-1":
                o["pos"] = {"x": 0, "y": 0}
                o["priority"] = 1
            else:
                o["enabled"] = False
        outs = helper.connected_outputs(cfg)
        args = helper.build_extend_args(outs, layout)
        for o in self.outputs:
            n = o["name"]
            self.assertIn(f"output.{n}.enable", args)
            self.assertIn(f"output.{n}.mode.{o['currentModeId']}", args)
            self.assertIn(f"output.{n}.position.{o['pos']['x']},{o['pos']['y']}", args)
            self.assertIn(f"output.{n}.rotation.{helper.ROTATIONS[o['rotation']]}", args)
            self.assertIn(f"output.{n}.priority.{o['priority']}", args)
        self.assertIn("output.DP-1.position.0,538", args)
        self.assertIn("output.DP-2.position.2560,538", args)
        self.assertIn("output.HDMI-A-2.position.5120,0", args)

    def test_extend_without_layout_places_side_by_side(self):
        args = helper.build_extend_args(self.outputs, None)
        self.assertEqual(sum(a.endswith(".enable") for a in args), 3)
        self.assertIn("output.DP-1.position.0,0", args)
        # HDMI-A-2 está girado: ocupa el alto del modo como ancho.
        positions = [a for a in args if ".position." in a]
        self.assertEqual(len(positions), 3)

    def test_extend_uses_one_atomic_command(self):
        layout = helper.snapshot(self.outputs)
        helper.save_layout(self.session_dir(), helper.layout_key(self.outputs), layout)
        code, res = run_cli("--dry-run", "--input", str(FIXTURE),
                            "--layout-dir", str(self.layout_dir), "extend")
        self.assertEqual(code, 0)
        self.assertEqual(res["command"][0], "kscreen-doctor")
        self.assertEqual(sum(a.endswith(".enable") for a in res["command"]), 3)


class ModeResolutionTests(BaseCase):
    def test_changed_mode_id_is_resolved_by_values(self):
        layout = helper.snapshot(self.outputs)
        cfg = copy.deepcopy(self.cfg)
        dp2 = next(o for o in cfg["outputs"] if o["name"] == "DP-2")
        old_id = dp2["currentModeId"]
        # Simula que RandR renumera los modos en otra sesión.
        for m in dp2["modes"]:
            m["id"] = f"x{m['id']}"
        dp2["currentModeId"] = f"x{old_id}"
        dp2["preferredModes"] = [f"x{p}" for p in dp2.get("preferredModes", [])]
        outs = helper.connected_outputs(cfg)
        args = helper.build_single_args(outs, "DP-2", layout)
        self.assertIn(f"output.DP-2.mode.x{old_id}", args)

    def test_nearest_refresh_within_same_size(self):
        dp1 = self.by_name["DP-1"]
        info = helper.current_mode_info(dp1)
        shifted = dict(info, refresh=info["refresh"] + 0.3)
        self.assertEqual(helper.resolve_mode_id(dp1, shifted), str(dp1["currentModeId"]))

    def test_unknown_size_returns_none(self):
        self.assertIsNone(helper.resolve_mode_id(self.by_name["DP-1"],
                                                 {"width": 1, "height": 1, "refresh": 60}))


class StatusAndLayoutTests(BaseCase):
    def test_status_saves_layout_when_extended(self):
        code, res = run_cli("--input", str(FIXTURE), "--layout-dir", str(self.layout_dir), "status")
        self.assertEqual(code, 0)
        self.assertEqual(res["mode"], "extend")
        self.assertTrue(res["layoutSaved"])
        self.assertEqual([o["name"] for o in res["outputs"]], ["DP-1", "DP-2", "HDMI-A-2"])
        hdmi = next(o for o in res["outputs"] if o["name"] == "HDMI-A-2")
        self.assertIn("vertical", hdmi["description"])

    def test_status_does_not_overwrite_layout_in_single_mode(self):
        key = helper.layout_key(self.outputs)
        helper.save_layout(self.session_dir(), key, helper.snapshot(self.outputs))
        cfg = copy.deepcopy(self.cfg)
        for o in cfg["outputs"]:
            if o["name"] == "DP-2":
                o["pos"] = {"x": 0, "y": 0}
            else:
                o["enabled"] = False
        code, res = run_cli("--input", self.write_cfg(cfg), "--layout-dir", str(self.layout_dir), "status")
        self.assertEqual(res["mode"], "single:DP-2")
        saved = helper.load_layout(self.session_dir(), key)
        self.assertEqual(saved["outputs"]["DP-2"]["pos"], {"x": 2560, "y": 538})

    def test_layout_key_depends_on_connected_set(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["outputs"] = [o for o in cfg["outputs"] if o["name"] != "HDMI-A-2"]
        self.assertNotEqual(helper.layout_key(self.outputs),
                            helper.layout_key(helper.connected_outputs(cfg)))

    def test_detect_modes(self):
        self.assertEqual(helper.detect_mode(self.outputs), "extend")
        outs = copy.deepcopy(self.outputs)
        outs[0]["enabled"] = False
        self.assertEqual(helper.detect_mode(outs), "partial")
        outs[1]["enabled"] = False
        self.assertEqual(helper.detect_mode(outs), f"single:{outs[2]['name']}")


class ProblemTests(BaseCase):
    def test_x11_and_wayland_are_supported(self):
        for session in ("x11", "wayland"):
            with mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": session}):
                codes = [p["code"] for p in helper.check_problems()]
            self.assertNotIn("unsupported-session", codes, session)

    def test_unknown_session_reported(self):
        with mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "tty"}):
            codes = [p["code"] for p in helper.check_problems()]
        self.assertIn("unsupported-session", codes)

    def test_missing_kscreen_doctor_reported(self):
        with mock.patch.dict(os.environ, {"PATH": ""}):
            codes = [p["code"] for p in helper.check_problems()]
        self.assertEqual(codes, ["missing-kscreen-doctor"])

    def test_apply_blocked_on_unsupported_session(self):
        code, res = run_cli("--input", str(FIXTURE), "--layout-dir", str(self.layout_dir),
                            "single", "DP-1", env={"XDG_SESSION_TYPE": "tty"})
        self.assertEqual(code, 1)
        self.assertFalse(res["ok"])
        self.assertIn("Wayland", res["error"])

    def test_unsupported_session_does_not_save_layout(self):
        ctx = helper.Context(mock.Mock(input=None, layout_dir=str(self.layout_dir), dry_run=False))
        with mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "tty"}):
            ctx.remember_if_extended(self.outputs, "k")
        self.assertFalse(self.layout_dir.exists())


class WaylandTests(BaseCase):
    def with_scale(self, name, scale):
        cfg = copy.deepcopy(self.cfg)
        for o in cfg["outputs"]:
            if o["name"] == name:
                o["scale"] = scale
        return cfg

    def test_wayland_restores_scale(self):
        outs = helper.connected_outputs(self.with_scale("DP-1", 1.25))
        layout = helper.snapshot(outs)
        args = helper.build_extend_args(outs, layout, session="wayland")
        self.assertIn("output.DP-1.scale.1.25", args)
        self.assertIn("output.DP-2.scale.1", args)

    def test_wayland_single_keeps_scale(self):
        outs = helper.connected_outputs(self.with_scale("HDMI-A-2", 1.5))
        args = helper.build_single_args(outs, "HDMI-A-2", helper.snapshot(outs), session="wayland")
        self.assertIn("output.HDMI-A-2.scale.1.5", args)
        self.assertIn("output.HDMI-A-2.rotation.right", args)

    def test_x11_never_sets_scale(self):
        outs = helper.connected_outputs(self.with_scale("DP-1", 1.25))
        args = helper.build_extend_args(outs, helper.snapshot(outs), session="x11")
        self.assertFalse(any(".scale." in a for a in args))

    def test_fallback_uses_logical_width_with_scale(self):
        outs = helper.connected_outputs(self.with_scale("DP-1", 2))
        args = helper.build_extend_args(outs, None, session="wayland")
        dp1 = self.by_name["DP-1"]
        w = helper.mode_to_info(helper.find_mode(dp1, helper.preferred_mode_id(dp1)))["width"]
        self.assertIn(f"output.DP-2.position.{w // 2},0", args)

    def test_layouts_are_separated_by_session(self):
        for session in ("x11", "wayland"):
            code, res = run_cli("--input", str(FIXTURE), "--layout-dir", str(self.layout_dir),
                                "status", env={"XDG_SESSION_TYPE": session})
            self.assertEqual(code, 0)
            self.assertTrue(res["layoutSaved"])
        key = helper.layout_key(self.outputs)
        self.assertTrue((self.session_dir("x11") / f"{key}.json").exists())
        self.assertTrue((self.session_dir("wayland") / f"{key}.json").exists())

    def test_wayland_description_shows_scale(self):
        outs = helper.connected_outputs(self.with_scale("DP-1", 1.25))
        ui = helper.outputs_for_ui(outs, None, "wayland")
        self.assertIn("125 %", next(o for o in ui if o["name"] == "DP-1")["description"])

    def test_flipped_rotation_is_preserved(self):
        cfg = copy.deepcopy(self.cfg)
        for o in cfg["outputs"]:
            if o["name"] == "DP-1":
                o["rotation"] = 32
        outs = helper.connected_outputs(cfg)
        args = helper.build_single_args(outs, "DP-1", helper.snapshot(outs), session="wayland")
        self.assertIn("output.DP-1.rotation.flipped90", args)


if __name__ == "__main__":
    unittest.main()
