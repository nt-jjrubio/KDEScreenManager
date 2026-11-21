// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// Una opción del desplegable: radio + título + subtítulo.
PlasmaComponents3.ItemDelegate {
    id: item

    property string title
    property string subtitle
    property string iconName: "video-display"
    property bool selected: false

    Layout.fillWidth: true
    highlighted: selected

    contentItem: RowLayout {
        spacing: Kirigami.Units.smallSpacing * 2

        PlasmaComponents3.RadioButton {
            checked: item.selected
            enabled: item.enabled
            // El estado lo decide el script; el clic se delega en el delegate.
            onClicked: { checked = Qt.binding(() => item.selected); item.clicked(); }
        }

        Kirigami.Icon {
            source: item.iconName
            Layout.preferredWidth: Kirigami.Units.iconSizes.medium
            Layout.preferredHeight: Kirigami.Units.iconSizes.medium
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0

            PlasmaComponents3.Label {
                Layout.fillWidth: true
                text: item.title
                font.bold: item.selected
                elide: Text.ElideRight
            }
            PlasmaComponents3.Label {
                Layout.fillWidth: true
                visible: text.length > 0
                text: item.subtitle
                opacity: 0.7
                font: Kirigami.Theme.smallFont
                elide: Text.ElideRight
            }
        }
    }
}
