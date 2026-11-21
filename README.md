# KDEScreenManager

Plasmoid para la bandeja del sistema de **KDE Plasma 6** que permite, con un clic:

- **Extender**: usar todos los monitores conectados.
- **Solo uno**: usar únicamente el monitor elegido y apagar el resto.

Al cambiar de modo se conservan la **alineación**, la **resolución**, la **frecuencia**, la **rotación**, el **monitor principal** y, en Wayland, la **escala** de cada pantalla.

> Funciona en sesiones **Plasma (Wayland)** y **Plasma (X11)**.

## Requisitos
- KDE Plasma 6 (sesión Wayland o X11).
- `kscreen-doctor` (paquete `libkscreen-bin`) y `python3`.

## Instalación (.deb)
Descarga el `.deb` de la [última release](https://github.com/nt-jjrubio/KDEScreenManager/releases/latest) e instálalo:
```sh
sudo apt install ./kdescreenmanager_*_all.deb
```

También puedes construirlo desde el código:
```sh
./packaging/build-deb.sh
sudo apt install ./build/kdescreenmanager_*_all.deb
```

El icono aparece solo en la bandeja del sistema. Si no aparece, reinicia Plasma (`plasmashell --replace &`) o actívalo en **Bandeja del sistema → Configurar → Elementos → KDEScreenManager → Mostrar siempre**.

Si falta Plasma 6, el instalador avisa, pero no falla.

Desinstalar: `sudo apt remove kdescreenmanager`. Las disposiciones guardadas se conservan en `~/.config/kdescreenmanager/`.

## Cómo funciona
- `package/contents/code/kdescreenmanager-helper.py` lee el estado con `kscreen-doctor -j` y aplica los cambios en **una sola** llamada a `kscreen-doctor`. Es la misma vía que usa Configuración del sistema, así que KScreen no revierte los cambios.
- Cada vez que todos los monitores están activos, el script guarda la disposición en `~/.config/kdescreenmanager/layouts/<sesión>/<hash>.json`. Hay una disposición por cada tipo de sesión (`x11` o `wayland`) y por cada combinación de monitores conectados. X11 y Wayland van separados porque usan escalas y coordenadas distintas.
- En Wayland también se guarda y restaura la escala de cada monitor. En X11 la escala es global y no se toca.
- Los modos se guardan como ancho, alto y frecuencia, no como id, porque los ids de RandR pueden cambiar entre sesiones.

Uso manual del script:
```sh
H=package/contents/code/kdescreenmanager-helper.py
python3 $H status
python3 $H --dry-run single DP-1   # muestra el comando sin aplicarlo
python3 $H extend
```

## Desarrollo
```sh
python3 -m unittest tests/test_helper.py   # tests (no tocan las pantallas)
./dev-install.sh                           # instala la copia local en ~/.local
plasmawindowed org.kdescreenmanager.applet # prueba el widget en una ventana
./dev-install.sh --remove                  # quita la copia local
```
No uses la copia local a la vez que el `.deb`: la copia local tapa a la del sistema.

## Versiones
La versión está en `package/metadata.json`. Para publicar una:
1. Sube la versión en `metadata.json`.
2. Añade una entrada en `CHANGELOG.md`.
3. Haz commit y crea la etiqueta `vX.Y.Z`.
4. Ejecuta `./packaging/build-deb.sh`.

Los paquetes construidos con cambios sin confirmar llevan el sufijo `+git<hash>` en la versión.
