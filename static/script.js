(function () {
    const infoButton = document.getElementById("infoButton");
    const infoModal = document.getElementById("infoModal");
    const energyModal = document.getElementById("energyModal");
    const chatMessages = document.getElementById("chatMessages");

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

    if (chatMessages) {
        const observer = new MutationObserver(decorateWelcomeBubble);
        observer.observe(chatMessages, { childList: true, subtree: true });
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

        if (document.getElementById("chatShell")?.classList.contains("chat-open")) {
            window.personalAiDashboard?.closeAI?.();
        }
    });

    decorateWelcomeBubble();
})();
