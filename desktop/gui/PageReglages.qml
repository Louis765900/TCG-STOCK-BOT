import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import App 1.0

// Réglages de l'appli : connexion Discord, enseignes, comportement.
Item {
    id: page
    property string confirmation: ""

    function charger() {
        var r = bridge.lireReglages()
        fToken.text = r.DISCORD_BOT_TOKEN || ""
        fChannel.text = r.DISCORD_CHANNEL_ID || ""
        fWebhook.text = r.DISCORD_WEBHOOK_URL || ""
        fRole.text = r.DISCORD_ALERT_ROLE_ID || ""
        fStores.text = r.ENABLED_STORES || ""
        fMin.text = r.MIN_SLEEP || ""
        fMax.text = r.MAX_SLEEP || ""
        fDeal.text = r.DEAL_DROP_PERCENT || ""
        fBeat.text = r.HEARTBEAT_INTERVAL || ""
        tMask.checked = ("" + (r.MASQUER_REVENDEURS || "")).toLowerCase() === "true"
        tAuto.checked = bridge.autostartActif()
    }
    function sauver() {
        bridge.enregistrerReglages({
            "DISCORD_BOT_TOKEN": fToken.text,
            "DISCORD_CHANNEL_ID": fChannel.text,
            "DISCORD_WEBHOOK_URL": fWebhook.text,
            "DISCORD_ALERT_ROLE_ID": fRole.text,
            "ENABLED_STORES": fStores.text,
            "MIN_SLEEP": fMin.text,
            "MAX_SLEEP": fMax.text,
            "DEAL_DROP_PERCENT": fDeal.text,
            "HEARTBEAT_INTERVAL": fBeat.text,
            "MASQUER_REVENDEURS": tMask.checked ? "true" : "false"
        })
        page.confirmation = "Réglages enregistrés ✓  (redémarre le bot pour tout appliquer)"
        masquerConfirm.restart()
    }
    Timer { id: masquerConfirm; interval: 4000; onTriggered: page.confirmation = "" }
    Component.onCompleted: charger()

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: parent.width
            spacing: Theme.gap

            // ---- Connexion Discord ----------------------------------------
            Card {
                Layout.fillWidth: true
                ColumnLayout {
                    width: parent.width
                    spacing: Theme.gap
                    Text { text: "Connexion Discord"; color: Theme.textHi
                           font { family: Theme.font; pixelSize: Theme.fsHead; weight: Font.DemiBold } }
                    Text {
                        text: "Mode bot (jeton + salon) = boutons cliquables. Sinon, un simple webhook suffit."
                        color: Theme.textDim; wrapMode: Text.Wrap; Layout.fillWidth: true
                        font { family: Theme.font; pixelSize: Theme.fsSmall }
                    }
                    Field { id: fToken; Layout.fillWidth: true; label: "Jeton du bot"; secret: true; placeholder: "Bot token (optionnel)" }
                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.gap
                        Field { id: fChannel; Layout.fillWidth: true; label: "ID du salon"; placeholder: "123456789..." }
                        Field { id: fRole; Layout.fillWidth: true; label: "ID du rôle à notifier"; placeholder: "(optionnel)" }
                    }
                    Field { id: fWebhook; Layout.fillWidth: true; label: "URL Webhook (alternative au bot)"; placeholder: "https://discord.com/api/webhooks/..." }
                }
            }

            // ---- Surveillance ---------------------------------------------
            Card {
                Layout.fillWidth: true
                ColumnLayout {
                    width: parent.width
                    spacing: Theme.gap
                    Text { text: "Surveillance"; color: Theme.textHi
                           font { family: Theme.font; pixelSize: Theme.fsHead; weight: Font.DemiBold } }
                    Field { id: fStores; Layout.fillWidth: true; label: "Enseignes actives (séparées par des virgules)"
                            placeholder: "Auchan,Leclerc,LudiJeux,RelicTCG,CoinBarons" }
                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.gap
                        Field { id: fMin; Layout.fillWidth: true; label: "Pause min (s)"; placeholder: "60" }
                        Field { id: fMax; Layout.fillWidth: true; label: "Pause max (s)"; placeholder: "180" }
                        Field { id: fDeal; Layout.fillWidth: true; label: "Seuil baisse prix (%)"; placeholder: "15" }
                        Field { id: fBeat; Layout.fillWidth: true; label: "Bilan auto (s, 0=off)"; placeholder: "86400" }
                    }
                    // Masquer revendeurs
                    Toggle {
                        id: tMask
                        Layout.fillWidth: true
                        titre: "Masquer les revendeurs (marketplace)"
                        sousTitre: "N'alerter que sur les vendeurs officiels."
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }

                    // Démarrage automatique avec Windows
                    Toggle {
                        id: tAuto
                        Layout.fillWidth: true
                        actif: bridge.autostartDisponible()
                        titre: "Démarrer avec Windows (24h/24)"
                        sousTitre: actif ? "L'appli se lance toute seule à l'ouverture de session."
                                         : "Disponible uniquement sous Windows."
                        onBasculer: function(v) { bridge.definirAutostart(v) }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: page.confirmation
                    color: Theme.green
                    font { family: Theme.font; pixelSize: Theme.fsSmall; weight: Font.DemiBold }
                }
                Item { Layout.fillWidth: true }
                AccentButton { text: "Recharger"; variant: "ghost"; onClicked: page.charger() }
                AccentButton { text: "Enregistrer"; onClicked: page.sauver() }
            }
        }
    }
}
