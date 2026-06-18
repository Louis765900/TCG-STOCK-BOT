import QtQuick
import QtQuick.Layouts
import App 1.0

// Interrupteur (on/off) avec libellé + sous-titre. Émet basculer(actif).
RowLayout {
    id: root
    property bool checked: false
    property string titre: ""
    property string sousTitre: ""
    property bool actif: true   // false = grisé/non interactif
    signal basculer(bool valeur)
    spacing: 12
    opacity: actif ? 1.0 : 0.45

    Rectangle {
        width: 46; height: 26; radius: 13
        color: root.checked ? Theme.accent : Theme.bg3
        Behavior on color { ColorAnimation { duration: Theme.anim } }
        Rectangle {
            width: 20; height: 20; radius: 10; color: Theme.textHi
            anchors.verticalCenter: parent.verticalCenter
            x: root.checked ? parent.width - width - 3 : 3
            Behavior on x { NumberAnimation { duration: Theme.anim; easing.type: Easing.OutCubic } }
        }
        MouseArea {
            anchors.fill: parent
            enabled: root.actif
            cursorShape: Qt.PointingHandCursor
            onClicked: { root.checked = !root.checked; root.basculer(root.checked) }
        }
    }
    ColumnLayout {
        spacing: 0
        Text { text: root.titre; color: Theme.text
               font { family: Theme.font; pixelSize: Theme.fsBody } }
        Text { text: root.sousTitre; visible: root.sousTitre !== ""; color: Theme.textDim
               font { family: Theme.font; pixelSize: Theme.fsSmall } }
    }
}
