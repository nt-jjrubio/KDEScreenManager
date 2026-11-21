// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    // Último estado devuelto por el script auxiliar.
    property var outputs: []
    property var problems: []
    property string mode: ""
    property bool busy: false
    property string lastError: ""

    readonly property bool hasProblems: problems.length > 0
    readonly property string helperPath:
        Qt.resolvedUrl("../code/kdescreenmanager-helper.py").toString().replace(/^file:\/\//, "")

    Plasmoid.icon: "video-display"
    Plasmoid.status: PlasmaCore.Types.ActiveStatus

    toolTipMainText: "KDEScreenManager"
    toolTipSubText: {
        if (hasProblems) return problems[0].message;
        if (mode === "extend") return i18np("Extendido (%1 monitor)", "Extendido (%1 monitores)", outputs.length);
        if (mode.startsWith("single:")) return i18n("Solo %1", mode.substring(7));
        if (mode === "partial") return i18n("Configuración personalizada");
        return "";
    }

    // ------------------------------------------------------------------
    // Ejecución del script auxiliar
    // ------------------------------------------------------------------
    property var pending: ({})

    P5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []

        onNewData: (sourceName, data) => {
            const callback = root.pending[sourceName];
            delete root.pending[sourceName];
            disconnectSource(sourceName);
            let result = null;
            try {
                result = JSON.parse(data["stdout"]);
            } catch (e) {
                result = { ok: false, error: i18n("Respuesta no válida del script auxiliar: %1", (data["stderr"] || data["stdout"] || "").trim()) };
            }
            if (callback) callback(result);
        }
    }

    function shellQuote(s) {
        return "'" + String(s).replace(/'/g, "'\\''") + "'";
    }

    function runHelper(args, callback) {
        const cmd = "python3 " + shellQuote(helperPath) + " " + args.map(shellQuote).join(" ");
        if (pending[cmd] !== undefined) return;  // ya en curso
        pending[cmd] = callback;
        executable.connectSource(cmd);
    }

    function applyStatus(result) {
        if (result.outputs !== undefined) {
            outputs = result.outputs;
            problems = result.problems || [];
            mode = result.mode || "";
        }
    }

    function refresh() {
        runHelper(["status"], result => {
            if (result.outputs === undefined && result.error) {
                problems = [{ code: "read-error", message: result.error }];
                return;
            }
            applyStatus(result);
        });
    }

    function select(key) {
        if (busy || hasProblems || key === mode) return;
        let args;
        if (key === "extend") {
            args = ["extend"];
        } else {
            const name = key.substring(7);
            if (!/^[A-Za-z0-9_.-]+$/.test(name)) return;
            args = ["single", name];
        }
        busy = true;
        lastError = "";
        runHelper(args, result => {
            busy = false;
            if (!result.ok && result.error) lastError = result.error;
            applyStatus(result);
            if (result.outputs === undefined) refresh();
        });
    }

    Component.onCompleted: refresh()
    onExpandedChanged: if (root.expanded) { lastError = ""; refresh(); }

    Timer {
        interval: 5000
        repeat: true
        running: root.expanded && !root.busy
        onTriggered: root.refresh()
    }

    // ------------------------------------------------------------------
    // Icono en la bandeja
    // ------------------------------------------------------------------
    compactRepresentation: MouseArea {
        hoverEnabled: true
        onClicked: root.expanded = !root.expanded

        Kirigami.Icon {
            anchors.fill: parent
            source: Plasmoid.icon
            active: parent.containsMouse
        }
        Kirigami.Icon {
            visible: root.hasProblems
            source: "emblem-warning"
            width: parent.width / 2
            height: width
            anchors.right: parent.right
            anchors.bottom: parent.bottom
        }
    }

    // ------------------------------------------------------------------
    // Desplegable
    // ------------------------------------------------------------------
    fullRepresentation: PlasmaExtras.Representation {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 18
        Layout.minimumHeight: Kirigami.Units.gridUnit * 10
        Layout.preferredHeight: implicitHeight
        collapseMarginsHint: true

        header: PlasmaExtras.PlasmoidHeading {
            RowLayout {
                anchors.fill: parent
                Kirigami.Heading {
                    Layout.fillWidth: true
                    level: 1
                    text: i18n("Pantallas")
                }
                PlasmaComponents3.BusyIndicator {
                    visible: root.busy
                    running: root.busy
                    Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                    Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                }
            }
        }

        contentItem: ColumnLayout {
            spacing: Kirigami.Units.smallSpacing

            PlasmaExtras.PlaceholderMessage {
                visible: root.hasProblems
                Layout.fillWidth: true
                Layout.margins: Kirigami.Units.largeSpacing
                iconName: "dialog-warning"
                text: root.hasProblems ? root.problems[0].message : ""
                explanation: root.problems.slice(1).map(p => p.message).join("\n")
            }

            OutputItem {
                visible: root.outputs.length > 0
                enabled: !root.hasProblems && !root.busy
                iconName: "preferences-desktop-display-randr"
                title: i18n("Extender: usar todas")
                subtitle: i18np("%1 monitor", "%1 monitores", root.outputs.length)
                selected: root.mode === "extend"
                onClicked: root.select("extend")
            }

            Kirigami.Separator {
                visible: root.outputs.length > 0
                Layout.fillWidth: true
            }

            Repeater {
                model: root.outputs
                delegate: OutputItem {
                    required property var modelData
                    enabled: !root.hasProblems && !root.busy
                    title: i18n("Solo %1", modelData.name)
                    subtitle: modelData.description + (modelData.primary ? " · " + i18n("principal") : "")
                    iconName: modelData.rotation === "left" || modelData.rotation === "right"
                              ? "monitor" : "video-display"
                    selected: root.mode === "single:" + modelData.name
                    onClicked: root.select("single:" + modelData.name)
                }
            }

            PlasmaComponents3.Label {
                visible: root.lastError.length > 0
                Layout.fillWidth: true
                Layout.margins: Kirigami.Units.smallSpacing
                text: root.lastError
                color: Kirigami.Theme.negativeTextColor
                wrapMode: Text.WordWrap
            }

            Item { Layout.fillHeight: true }
        }
    }
}
