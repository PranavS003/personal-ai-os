document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    const input = document.getElementById(button.getAttribute("aria-controls"));
    const label = input.labels[0].textContent.trim().toLowerCase();

    button.hidden = false;
    button.addEventListener("click", () => {
        const showPassword = input.type === "password";
        input.type = showPassword ? "text" : "password";
        button.textContent = showPassword ? "Hide" : "Show";
        button.setAttribute("aria-label", `${button.textContent} ${label}`);
    });
});
