import QtQuick
import App 1.0

// Élément de navigation de la barre latérale (icône emoji + libellé).
Item {
    id: root
    property string icone: ""
    property string label: ""
    property bool actif: false
    signal clicked()

    implicitHeight: 44
    width: parent ? parent.width : 200

    Rectangle {
        id: fond
        anchors.fill: parent
        radius: Theme.radius
        color: root.actif ? Theme.bg2 : (ma.containsMouse ? Theme.bg1 : "transparent")
        Behavior on color { ColorAnimation { duration: Theme.anim } }

        // Barre d'accent à gauche quand actif.
        Rectangle {
            anchors { left: parent.left; verticalCenter: parent.verticalCenter }
            width: 3; height: root.actif ? 22 : 0
            radius: 2
            color: Theme.accent
            Behavior on height { NumberAnimation { duration: Theme.anim; easing.type: Easing.OutCubic } }
        }
    }

    Row {
        anchors.fill: parent
        anchors.leftMargin: 14
        spacing: 12
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.icone
            font.pixelSize: 18
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.label
            color: root.actif ? Theme.textHi : Theme.text
            font { family: Theme.font; pixelSize: Theme.fsBody; weight: root.actif ? Font.DemiBold : Font.Normal }
            Behavior on color { ColorAnimation { duration: Theme.anim } }
        }
    }

    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
