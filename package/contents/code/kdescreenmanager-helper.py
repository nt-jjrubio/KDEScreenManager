#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Script auxiliar de KDEScreenManager.

Lee la configuración de pantallas con `kscreen-doctor -j`, guarda la
disposición de los monitores cuando están todos activos y aplica los modos
"extender" o "solo un monitor" con una única llamada a `kscreen-doctor`.
Funciona en sesiones Plasma X11 y Wayland.

Siempre escribe un objeto JSON en stdout para que el plasmoid lo procese.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

KSCREEN = "kscreen-doctor"
LAYOUT_VERSION = 2
SUPPORTED_SESSIONS = ("x11", "wayland")

# Valores de rotación del JSON de libkscreen -> argumento de kscreen-doctor
ROTATIONS = {
    1: "none", 2: "left", 4: "inverted", 8: "right",
    16: "flipped", 32: "flipped90", 64: "flipped180", 128: "flipped270",
}
ROTATION_LABELS = {
    "none": "", "left": "vertical", "right": "vertical", "inverted": "invertido",
    "flipped": "volteado", "flipped90": "vertical, volteado",
    "flipped180": "invertido, volteado", "flipped270": "vertical, volteado",
}
PORTRAIT = ("left", "right", "flipped90", "flipped270")


class HelperError(Exception):
    """Error que se devuelve al plasmoid como mensaje legible."""


# --------------------------------------------------------------------------
# Lectura del estado
# --------------------------------------------------------------------------

def session_type():
    return os.environ.get("XDG_SESSION_TYPE", "").lower()


def read_kscreen(input_file=None):
    """Devuelve el JSON de kscreen-doctor (o de un fichero, para tests)."""
    if input_file:
        with open(input_file, encoding="utf-8") as fh:
            return json.load(fh)
    try:
        res = subprocess.run([KSCREEN, "-j"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HelperError(f"No se pudo ejecutar kscreen-doctor: {exc}") from exc
    if res.returncode != 0:
        raise HelperError(f"kscreen-doctor -j terminó con código {res.returncode}: {res.stderr.strip()}")
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError as exc:
        raise HelperError(f"kscreen-doctor devolvió un JSON no válido: {exc}") from exc


def connected_outputs(cfg):
    outs = [o for o in cfg.get("outputs", []) if o.get("connected")]
    return sorted(outs, key=lambda o: o["name"])


def rotation_of(output):
    return ROTATIONS.get(output.get("rotation", 1), "none")


def find_mode(output, mode_id):
    for m in output.get("modes", []):
        if str(m.get("id")) == str(mode_id):
            return m
    return None


def mode_to_info(mode):
    return {
        "width": mode["size"]["width"],
        "height": mode["size"]["height"],
        "refresh": round(float(mode["refreshRate"]), 3),
    }


def current_mode_info(output):
    mode = find_mode(output, output.get("currentModeId"))
    if mode is None:
        prefs = output.get("preferredModes") or []
        mode = find_mode(output, prefs[0]) if prefs else None
    if mode is None and output.get("modes"):
        mode = output["modes"][0]
    return mode_to_info(mode) if mode else None


def resolve_mode_id(output, info):
    """Busca el id de modo actual que coincide con ancho/alto/refresco.

    Los ids de modo pueden cambiar entre sesiones (sobre todo en X11), por
    eso la disposición se guarda por valores y se resuelve al aplicar.
    Se elige la frecuencia más cercana entre los modos del mismo tamaño.
    """
    if not info:
        return None
    same_size = [
        m for m in output.get("modes", [])
        if m["size"]["width"] == info["width"] and m["size"]["height"] == info["height"]
    ]
    if not same_size:
        return None
    best = min(same_size, key=lambda m: abs(float(m["refreshRate"]) - info["refresh"]))
    return str(best["id"])


def preferred_mode_id(output):
    prefs = output.get("preferredModes") or []
    if prefs:
        return str(prefs[0])
    modes = output.get("modes") or []
    if not modes:
        return None
    best = max(modes, key=lambda m: (m["size"]["width"] * m["size"]["height"], m["refreshRate"]))
    return str(best["id"])


def format_scale(scale):
    return f"{float(scale):g}"


# --------------------------------------------------------------------------
# Disposiciones guardadas
# --------------------------------------------------------------------------

def default_layout_base():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "kdescreenmanager" / "layouts"


def layout_key(outputs):
    """Identifica la combinación de monitores conectados."""
    parts = []
    for o in outputs:
        mm = o.get("sizeMM") or {}
        parts.append(f"{o['name']}:{mm.get('width', 0)}x{mm.get('height', 0)}")
    return hashlib.sha1("|".join(sorted(parts)).encode()).hexdigest()[:16]


def snapshot(outputs):
    data = {}
    for o in outputs:
        data[o["name"]] = {
            "mode": current_mode_info(o),
            "pos": {"x": o["pos"]["x"], "y": o["pos"]["y"]},
            "rotation": rotation_of(o),
            "priority": o.get("priority", 0),
            "scale": float(o.get("scale", 1) or 1),
        }
    return {"version": LAYOUT_VERSION, "outputs": data}


def load_layout(layout_dir, key):
    path = Path(layout_dir) / f"{key}.json"
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("version") != LAYOUT_VERSION or "outputs" not in data:
        return None
    return data


def save_layout(layout_dir, key, layout):
    path = Path(layout_dir)
    path.mkdir(parents=True, exist_ok=True)
    tmp = path / f".{key}.json.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(layout, fh, indent=2, sort_keys=True)
    os.replace(tmp, path / f"{key}.json")


def is_extended(outputs):
    return len(outputs) >= 2 and all(o.get("enabled") for o in outputs)


def detect_mode(outputs):
    enabled = [o for o in outputs if o.get("enabled")]
    if len(outputs) <= 1 or len(enabled) == len(outputs):
        return "extend"
    if len(enabled) == 1:
        return f"single:{enabled[0]['name']}"
    return "partial"


# --------------------------------------------------------------------------
# Construcción de comandos
# --------------------------------------------------------------------------

def _logical_width(info, rotation, scale):
    """Ancho que ocupa el monitor en el escritorio (coordenadas lógicas)."""
    if not info:
        return 0
    width = info["height"] if rotation in PORTRAIT else info["width"]
    return int(round(width / (scale or 1)))


def _output_args(name, mode_id, rotation, pos, priority, scale, session):
    args = [f"output.{name}.enable"]
    if mode_id:
        args.append(f"output.{name}.mode.{mode_id}")
    # En X11 la escala es global: solo se toca en Wayland.
    if session == "wayland" and scale:
        args.append(f"output.{name}.scale.{format_scale(scale)}")
    args.append(f"output.{name}.rotation.{rotation}")
    args.append(f"output.{name}.position.{pos[0]},{pos[1]}")
    args.append(f"output.{name}.priority.{priority}")
    return args


def build_extend_args(outputs, layout, session=None):
    session = session if session is not None else session_type()
    args = []
    saved = (layout or {}).get("outputs", {})
    if saved and all(o["name"] in saved for o in outputs):
        ordered = sorted(outputs, key=lambda o: (saved[o["name"]].get("priority") or 99, o["name"]))
        for prio, o in enumerate(ordered, start=1):
            s = saved[o["name"]]
            mode_id = resolve_mode_id(o, s.get("mode")) or preferred_mode_id(o)
            args += _output_args(o["name"], mode_id, s.get("rotation", "none"),
                                 (s["pos"]["x"], s["pos"]["y"]), prio, s.get("scale", 1), session)
        return args

    # Sin disposición guardada: todos en fila, de izquierda a derecha.
    x = 0
    ordered = sorted(outputs, key=lambda o: (o["pos"]["x"], o["name"]))
    for prio, o in enumerate(ordered, start=1):
        rotation = rotation_of(o)
        scale = float(o.get("scale", 1) or 1)
        mode_id = preferred_mode_id(o)
        mode = find_mode(o, mode_id) if mode_id else None
        args += _output_args(o["name"], mode_id, rotation, (x, 0), prio, scale, session)
        x += _logical_width(mode_to_info(mode) if mode else None, rotation, scale)
    return args


def build_single_args(outputs, target_name, layout, session=None):
    session = session if session is not None else session_type()
    target = next((o for o in outputs if o["name"] == target_name), None)
    if target is None:
        names = ", ".join(o["name"] for o in outputs) or "ninguno"
        raise HelperError(f"El monitor «{target_name}» no está conectado (conectados: {names})")

    saved = ((layout or {}).get("outputs") or {}).get(target_name)
    if saved:
        info, rotation, scale = saved.get("mode"), saved.get("rotation", "none"), saved.get("scale", 1)
    elif target.get("enabled"):
        info, rotation, scale = current_mode_info(target), rotation_of(target), target.get("scale", 1)
    else:
        info, rotation, scale = None, rotation_of(target), target.get("scale", 1)
    mode_id = resolve_mode_id(target, info) or preferred_mode_id(target)

    args = _output_args(target_name, mode_id, rotation, (0, 0), 1, scale, session)
    for o in outputs:
        if o["name"] != target_name:
            args.append(f"output.{o['name']}.disable")
    return args


# --------------------------------------------------------------------------
# Estado para la interfaz
# --------------------------------------------------------------------------

def describe(info, rotation, scale=1, session=""):
    if not info:
        return ""
    parts = [f"{info['width']}×{info['height']} @ {round(info['refresh'])} Hz"]
    if session == "wayland" and scale and abs(float(scale) - 1) > 1e-6:
        parts.append(f"{round(float(scale) * 100)} %")
    label = ROTATION_LABELS.get(rotation, "")
    if label:
        parts.append(label)
    return " · ".join(parts)


def outputs_for_ui(outputs, layout, session=""):
    saved = (layout or {}).get("outputs", {})
    result = []
    for o in outputs:
        s = saved.get(o["name"])
        if o.get("enabled") or not s:
            info, rotation, scale = current_mode_info(o), rotation_of(o), o.get("scale", 1)
        else:
            info, rotation, scale = s.get("mode"), s.get("rotation", "none"), s.get("scale", 1)
        result.append({
            "name": o["name"],
            "enabled": bool(o.get("enabled")),
            "primary": o.get("priority") == 1 and bool(o.get("enabled")),
            "mode": info,
            "rotation": rotation,
            "scale": scale,
            "description": describe(info, rotation, scale, session),
        })
    return result


def check_problems(cfg_error=None, ignore_session=False):
    problems = []
    if shutil.which(KSCREEN) is None:
        problems.append({
            "code": "missing-kscreen-doctor",
            "message": "Falta kscreen-doctor. Instálalo con: sudo apt install libkscreen-bin",
        })
    if not ignore_session and session_type() not in SUPPORTED_SESSIONS:
        problems.append({
            "code": "unsupported-session",
            "message": "Tipo de sesión no compatible. Inicia sesión en Plasma (Wayland) o Plasma (X11).",
        })
    if cfg_error:
        problems.append({"code": "read-error", "message": str(cfg_error)})
    return problems


class Context:
    def __init__(self, args):
        self.input_file = args.input
        base = Path(args.layout_dir) if args.layout_dir else default_layout_base()
        # Una carpeta por tipo de sesión: X11 y Wayland usan coordenadas y
        # escalas distintas, así que sus disposiciones no se mezclan.
        self.layout_dir = base / (session_type() or "other")
        self.dry_run = args.dry_run

    def read(self):
        cfg = read_kscreen(self.input_file)
        outputs = connected_outputs(cfg)
        return outputs, layout_key(outputs)

    def remember_if_extended(self, outputs, key):
        """Guarda la disposición si todos los monitores están activos."""
        if self.dry_run:
            return
        if session_type() not in SUPPORTED_SESSIONS and self.input_file is None:
            return
        if is_extended(outputs):
            try:
                save_layout(self.layout_dir, key, snapshot(outputs))
            except OSError:
                pass

    def status(self):
        cfg_error = None
        outputs, key = [], None
        try:
            outputs, key = self.read()
        except HelperError as exc:
            cfg_error = exc
        problems = check_problems(cfg_error, ignore_session=self.input_file is not None)
        if key:
            self.remember_if_extended(outputs, key)
        layout = load_layout(self.layout_dir, key) if key else None
        return {
            "ok": not problems,
            "session": session_type(),
            "problems": problems,
            "mode": detect_mode(outputs) if outputs else None,
            "layoutSaved": layout is not None,
            "outputs": outputs_for_ui(outputs, layout, session_type()),
        }

    def apply(self, build):
        if not self.dry_run:
            problems = check_problems()
            if problems:
                raise HelperError(problems[0]["message"])
        outputs, key = self.read()
        if not outputs:
            raise HelperError("No hay ningún monitor conectado")
        self.remember_if_extended(outputs, key)
        layout = load_layout(self.layout_dir, key)
        args = build(outputs, layout)
        if not any(a.endswith(".enable") for a in args):
            raise HelperError("La configuración dejaría todos los monitores apagados")
        command = [KSCREEN] + args
        if self.dry_run:
            return {"ok": True, "dryRun": True, "command": command}
        try:
            res = subprocess.run(command, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HelperError(f"No se pudo aplicar la configuración: {exc}") from exc
        if res.returncode != 0:
            raise HelperError(f"kscreen-doctor terminó con código {res.returncode}: {res.stderr.strip()}")
        result = self.status()
        result["command"] = command
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Script auxiliar de KDEScreenManager")
    parser.add_argument("--dry-run", action="store_true", help="muestra el comando sin ejecutarlo")
    parser.add_argument("--input", help=argparse.SUPPRESS)       # JSON de kscreen-doctor (tests)
    parser.add_argument("--layout-dir", help=argparse.SUPPRESS)  # carpeta de disposiciones (tests)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="estado actual en JSON")
    sub.add_parser("extend", help="extender: usar todos los monitores")
    single = sub.add_parser("single", help="usar solo un monitor")
    single.add_argument("name", help="nombre de la salida, p. ej. DP-1")
    args = parser.parse_args(argv)

    ctx = Context(args)
    try:
        if args.command == "status":
            result = ctx.status()
        elif args.command == "extend":
            result = ctx.apply(build_extend_args)
        else:
            result = ctx.apply(lambda outs, lay: build_single_args(outs, args.name, lay))
    except HelperError as exc:
        result = {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - nunca dejar al plasmoid sin respuesta
        result = {"ok": False, "error": f"Error inesperado: {exc}"}

    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
