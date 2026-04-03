(function () {
    const chatShell = document.getElementById("chatShell");
    const chatWidget = document.getElementById("chatWidget");
    const chatToggle = document.getElementById("chatToggle");
    const infoButton = document.getElementById("infoButton");
    const infoModal = document.getElementById("infoModal");
    const energyModal = document.getElementById("energyModal");
    const statusPane = document.querySelector(".status-pane");

    function syncChatShellState() {
        const isOpen = Boolean(chatWidget && !chatWidget.classList.contains("hidden"));
        chatShell?.classList.toggle("chat-open", isOpen);
        chatToggle?.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }

    function decorateWelcomeBubble() {
        const firstBotBubble = document.querySelector(".chat-message.bot .chat-bubble");
        firstBotBubble?.classList.add("welcome-bubble");
    }

    function openInfoModal() {
        if (!infoModal) {
            return;
        }

        infoModal.classList.remove("hidden");
        infoModal.setAttribute("aria-hidden", "false");
    }

    function closeInfoModal() {
        if (!infoModal) {
            return;
        }

        infoModal.classList.add("hidden");
        infoModal.setAttribute("aria-hidden", "true");
    }

    if (chatWidget) {
        const observer = new MutationObserver(syncChatShellState);
        observer.observe(chatWidget, { attributes: true, attributeFilter: ["class"] });
    }

    if (statusPane) {
        statusPane.setAttribute("data-enhanced", "true");
    }

    if (infoButton) {
        infoButton.addEventListener("click", openInfoModal);
    }

    document.querySelectorAll("[data-close-info-modal]").forEach((button) => {
        button.addEventListener("click", closeInfoModal);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") {
            return;
        }

        if (infoModal && !infoModal.classList.contains("hidden")) {
            closeInfoModal();
            return;
        }

        if (energyModal && !energyModal.classList.contains("hidden")) {
            window.personalAiDashboard?.closeEnergyModal?.();
            return;
        }

        if (chatWidget && !chatWidget.classList.contains("hidden")) {
            chatWidget.classList.add("hidden");
            chatShell?.classList.remove("chat-open");
            chatToggle?.setAttribute("aria-expanded", "false");
        }
    });

    syncChatShellState();
    decorateWelcomeBubble();
})();
