(function () {
    const chatShell = document.getElementById("chatShell");
    const chatWidget = document.getElementById("chatWidget");
    const chatToggle = document.getElementById("chatToggle");
    const infoButton = document.getElementById("infoButton");
    const infoModal = document.getElementById("infoModal");
    const energyModal = document.getElementById("energyModal");
    const aiModal = document.getElementById("aiModal");

    function syncChatShellState() {
        const isOpen = Boolean(chatWidget && !chatWidget.classList.contains("hidden"));
        chatShell?.classList.toggle("chat-open", isOpen);
        chatToggle?.setAttribute("aria-expanded", isOpen ? "true" : "false");
        aiModal?.classList.toggle("hidden", !isOpen);
        aiModal?.setAttribute("aria-hidden", isOpen ? "false" : "true");
        document.body.classList.toggle("ai-modal-open", isOpen);
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

        if (aiModal && !aiModal.classList.contains("hidden")) {
            window.personalAiDashboard?.closeAI?.();
        }
    });

    syncChatShellState();
    decorateWelcomeBubble();
})();
