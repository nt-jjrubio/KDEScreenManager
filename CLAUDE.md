# CLAUDE.md

Guía para trabajar en **KDEScreenManager**: un plasmoid de la bandeja del sistema de KDE Plasma 6 que cambia entre extender todos los monitores o usar solo uno, conservando la alineación, la resolución, la frecuencia, la rotación, el monitor principal y (en Wayland) la escala. Funciona en X11 y Wayland. Se distribuye como `.deb`.

El diseño completo está en `PLAN.md`. Los cambios de cada versión, en `CHANGELOG.md`.

## Estructura
- `package/`: paquete Plasma/Applet (Id `org.kdescreenmanager.applet`).
  - `metadata.json`: metadatos del plasmoid y **única fuente de la versión**.
  - `contents/ui/main.qml`: icono de la bandeja y desplegable. Llama al helper con `Plasma5Support.DataSource` (motor `executable`).
  - `contents/ui/OutputItem.qml`: fila de cada opción.
  - `contents/code/kdescreenmanager-helper.py`: toda la lógica. Comandos `status`, `extend`, `single <NOMBRE>` y `--dry-run`. Siempre devuelve JSON por stdout.
- `packaging/`: `build-deb.sh`, `control.in` y `postinst`.
- `tests/`: `test_helper.py` y `fixtures/three-monitors.json` (salida real de `kscreen-doctor -j`).
- `dev-install.sh`: instalación local con `kpackagetool6` (solo desarrollo).
- `LICENSE`: GPL-3.0-or-later (texto completo). `packaging/copyright` es el resumen que se instala con el `.deb`.

## Comandos
```sh
python3 -m unittest tests/test_helper.py                  # tests (no tocan las pantallas)
python3 package/contents/code/kdescreenmanager-helper.py status
python3 package/contents/code/kdescreenmanager-helper.py --dry-run single DP-1
./packaging/build-deb.sh                                   # → build/kdescreenmanager_<versión>_all.deb
./dev-install.sh [--remove]                                # copia local en ~/.local/share/plasma/plasmoids
plasmawindowed org.kdescreenmanager.applet                 # probar el widget en una ventana
```

## Reglas del proyecto
- **Backend único: `kscreen-doctor`**, en X11 y en Wayland. Todos los cambios van en **una sola llamada** (atómica). No usar `xrandr`, porque KScreen revertiría los cambios.
- **Nunca pasar texto sin validar a la shell.** En Python, `subprocess.run` con una lista de argumentos. En QML, argumentos entrecomillados con `shellQuote` y nombres de monitor validados con `^[A-Za-z0-9_.-]+$`.
- **Disposiciones guardadas**: `~/.config/kdescreenmanager/layouts/<sesión>/<hash>.json`. Hay una carpeta por sesión (`x11`/`wayland`) y un archivo por combinación de monitores. Los modos se guardan por ancho, alto y refresco, **nunca por id**. Si cambias el formato, sube `LAYOUT_VERSION`.
- **Escala**: solo se aplica en Wayland (en X11 es global).
- **Nunca dejar 0 monitores activos.**
- **Plasma no va en `Depends`** del `.deb` (solo `python3` y `libkscreen-bin`). Si falta, se avisa en `postinst`, que **siempre** termina con `exit 0`, y en el widget.
- El nombre del paquete Debian va en minúsculas (`kdescreenmanager`). El nombre visible es "KDEScreenManager".
- La interfaz y los mensajes están en **español**. En QML, los textos van con `i18n()`/`i18np()`.
- Python solo con la biblioteca estándar.

## Pruebas
- Los tests usan `--input` (fixture) y `--layout-dir` (carpeta temporal), y fijan `XDG_SESSION_TYPE`. **Ningún test debe llamar a `extend`/`single` sin `--dry-run` en una sesión compatible**, porque aplicaría cambios reales en las pantallas.
- Usa `--dry-run` para ver el comando sin aplicarlo.
- **Probar el cambio real de monitores solo con permiso del usuario.** Apaga pantallas. El procedimiento es guardar `kscreen-doctor -j` antes, cambiar de modo, volver a "Extender" y comparar posición, modo, rotación, prioridad y escala.
  - Recuperación: `python3 package/contents/code/kdescreenmanager-helper.py extend`.
- Estado: probado en vivo en Wayland (varios monitores, rotación y escala fraccionaria). **En X11 solo está probado con tests y dry-run.**

## Entorno de desarrollo
- Para instalar el `.deb` sin terminal interactiva (por ejemplo, desde una herramienta): `pkexec apt-get install --reinstall -y ./build/kdescreenmanager_<versión>_all.deb`, que abre la ventana de contraseña de KDE.
- No usar a la vez `dev-install.sh` y el `.deb`, porque la copia local tapa a la del sistema.
- Reiniciar Plasma: `systemctl --user restart plasma-plasmashell.service`. No editar `~/.config/plasma-org.kde.plasma.desktop-appletsrc` mientras Plasma está en ejecución.

## Git
- Rama principal: `main`. Remoto: `origin`.
- `PLAN.md` está en `.gitignore` a propósito: es local y no se sube. Tampoco se suben `build/` ni los `.deb`.
- Commits pequeños, uno por bloque de trabajo, con los mensajes en español.
- Hacer commit, `push`, crear etiquetas o publicar releases **solo cuando el usuario lo pida**.
- **El repositorio es público**: no escribir en archivos versionados, commits ni notas de release datos de cuentas, credenciales ni información personal o de la máquina local.
- El README enlaza a `releases/latest`, así que no hay que tocarlo en cada versión.

## Publicar una versión
1. Subir `KPlugin.Version` en `package/metadata.json`.
2. Pasar las entradas de "Sin publicar" a la nueva versión en `CHANGELOG.md`, con fecha.
3. Commit y etiqueta anotada: `git tag -a vX.Y.Z -m "KDEScreenManager X.Y.Z"`.
4. `git push origin main` y `git push origin vX.Y.Z`. `git push` no sube las etiquetas por defecto.
5. Construir el `.deb` con el árbol limpio: `rm -rf build && ./packaging/build-deb.sh`. Si hay cambios sin confirmar, la versión lleva el sufijo `+git<hash>`, y eso no debe publicarse.
6. Crear la release con el `.deb` adjunto:
   ```sh
   gh release create vX.Y.Z build/kdescreenmanager_X.Y.Z_all.deb \
     --title "KDEScreenManager X.Y.Z" --notes-file <notas.md> --verify-tag
   ```
   En las notas van las novedades del CHANGELOG y las instrucciones de instalación.

Versiones publicadas: `v0.1.0` y `v0.1.1` (2026-11-21).
