import QtQuick
import QtQuick.Controls.Basic
import App 1.0

// Champ de saisie étiqueté (libellé au-dessus + zone de texte arrondie, une ligne).
Column {
    id: root
    property string label: ""
    property alias text: input.text
    property alias placeholder: input.placeholderText
    property bool secret: false
    spacing: 6

    Text {
        text: root.label
        visible: root.label !== ""
        color: Theme.textDim
        font { family: Theme.font; pixelSize: Theme.fsSmall; weight: Font.DemiBold }
    }

    TextField {
        id: input
        width: parent.width
        height: 40
        color: Theme.text
        font { family: Theme.font; pixelSize: Theme.fsBody }
        echoMode: root.secret ? TextInput.Password : TextInput.Normal
        selectByMouse: true
        leftPadding: 12; rightPadding: 12
        placeholderTextColor: Theme.textDim
        background: Rectangle {
            radius: Theme.radiusSm
            color: Theme.bg2
            border.width: 1
            border.color: input.activeFocus ? Theme.accent : Theme.border
            Behavior on border.color { ColorAnimation { duration: Theme.anim } }
        }
    }
}
