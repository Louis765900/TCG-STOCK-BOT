import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import App 1.0

// Assistant de 1ère configuration : guide Tom pas à pas (sans toucher au code).
Item {
    id: page
    signal termine()
    property int etape: 0
    readonly property int nbEtapes: 3

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - 80, 620)
        spacing: Theme.pad

        // Indicateur d'étapes
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 8
            Repeater {
                model: page.nbEtapes
                delegate: Rectangle {
                    width: index === page.etape ? 26 : 9
                    height: 9; radius: 4
                    color: index <= page.etape ? Theme.accent : Theme.bg3
                    Behavior on width { NumberAnimation { duration: Theme.anim } }
                    Behavior on color { ColorAnimation { duration: Theme.anim } }
                }
            }
        }

        Card {
            Layout.fillWidth: true
            implicitHeight: pile.implicitHeight + 2 * Theme.pad

            StackLayout {
                id: pile
                anchors.fill: parent
                currentIndex: page.etape

                // --- Étape 0 : bienvenue ----------------------------------
                ColumnLayout {
                    spacing: Theme.gap
                    Text { text: "👋  Bienvenue !"; color: Theme.textHi
                           font { family: Theme.font; pixelSize: Theme.fsTitle; weight: Font.Bold } }
                    Text {
                        text: "Ce petit assistant va configurer le bot en 2 minutes. Il surveille les cartes "
                            + "Pokémon et One Piece (en français) sur plusieurs boutiques et te prévient sur "
                            + "Discord dès qu'un produit revient en stock ou baisse de prix.\n\nClique sur Suivant."
                        color: Theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true
                        font { family: Theme.font; pixelSize: Theme.fsBody; }
                        lineHeight: 1.3
                    }
                }

                // --- Étape 1 : connexion Discord --------------------------
                ColumnLayout {
                    spacing: Theme.gap
                    Text { text: "🔗  Connexion à Discord"; color: Theme.textHi
                           font { family: Theme.font; pixelSize: Theme.fsHead; weight: Font.Bold } }
                    Text {
                        text: "Le plus simple : colle l'URL d'un Webhook de ton salon Discord.\n"
                            + "(Salon → Paramètres → Intégrations → Webhooks → Nouveau webhook → Copier l'URL.)"
                        color: Theme.textDim; wrapMode: Text.Wrap; Layout.fillWidth: true
                        font { family: Theme.font; pixelSize: Theme.fsSmall }
                    }
                    Field { id: aWebhook; Layout.fillWidth: true; label: "URL du Webhook"
                            placeholder: "https://discord.com/api/webhooks/..." }

                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }

                    Text { text: "Ou mode bot (avancé — débloque les boutons cliquables) :"; color: Theme.textDim
                           font { family: Theme.font; pixelSize: Theme.fsSmall; weight: Font.DemiBold } }
                    Field { id: aToken; Layout.fillWidth: true; label: "Jeton du bot"; secret: true; placeholder: "(optionnel)" }
                    Field { id: aChannel; Layout.fillWidth: true; label: "ID du salon"; placeholder: "(optionnel)" }
                }

                // --- Étape 2 : terminé ------------------------------------
                ColumnLayout {
                    spacing: Theme.gap
                    Text { text: "✅  Tout est prêt !"; color: Theme.green
                           font { family: Theme.font; pixelSize: Theme.fsTitle; weight: Font.Bold } }
                    Text {
                        text: "On enregistre tes réglages. Tu pourras lancer la surveillance depuis l'accueil "
                            + "avec le bouton « Démarrer ». Le bot peut tourner 24h/24."
                        color: Theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true
                        font { family: Theme.font; pixelSize: Theme.fsBody }
                    }
                }
            }
        }

        // Navigation
        RowLayout {
            Layout.fillWidth: true
            AccentButton { text: "Retour"; variant: "ghost"; visible: page.etape > 0
                           onClicked: page.etape-- }
            Item { Layout.fillWidth: true }
            AccentButton {
                text: page.etape < page.nbEtapes - 1 ? "Suivant" : "Terminer"
                onClicked: {
                    if (page.etape === 1) {
                        // Sauve la connexion Discord saisie.
                        bridge.enregistrerReglages({
                            "DISCORD_WEBHOOK_URL": aWebhook.text,
                            "DISCORD_BOT_TOKEN": aToken.text,
                            "DISCORD_CHANNEL_ID": aChannel.text
                        })
                    }
                    if (page.etape < page.nbEtapes - 1) page.etape++
                    else page.termine()
                }
            }
        }
    }
}
