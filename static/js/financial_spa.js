(function () {
    const coachInsights = [
        {
            text: "AI Insight: Your spending on food is slightly high this week. Consider reducing Swiggy orders and redirecting \u20B9500 into savings.",
            meta: "Focused on your weekly habits",
        },
        {
            text: "AI Insight: You are staying consistent with essentials. Try moving \u20B9250 from impulse purchases into your emergency fund this weekend.",
            meta: "Updated after spending review",
        },
        {
            text: "AI Insight: Your subscriptions look stable. Review one unused plan this month and redirect the saved amount toward long-term investing.",
            meta: "Optimized for monthly clean-up",
        },
    ];

    function initFinancialPage(scope = document) {
        const root = scope.matches?.("[data-financial-root]")
            ? scope
            : scope.querySelector?.("[data-financial-root]");

        if (!root || root.dataset.financialBound === "true") {
            return;
        }

        root.dataset.financialBound = "true";

        const expenseForm = root.querySelector("#expenseLoggerForm");
        const amountInput = root.querySelector("#expenseAmount");
        const categorySelect = root.querySelector("#expenseCategory");
        const message = root.querySelector("#expenseLoggerMessage");
        const adviceButton = root.querySelector("#financialAdviceButton");
        const insightText = root.querySelector("#financialInsightText");
        const adviceMeta = root.querySelector("#financialAdviceMeta");
        const highlightCard = root.querySelector(".financial-card--highlight");
        let currentInsightIndex = 0;

        function setFormMessage(text, type = "") {
            if (!message) {
                return;
            }

            message.textContent = text;
            message.classList.remove("is-success", "is-error");
            if (type) {
                message.classList.add(type);
            }
        }

        expenseForm?.addEventListener("submit", (event) => {
            event.preventDefault();

            const amount = Number(amountInput?.value || 0);
            const category = categorySelect?.value || "";

            if (!amount || amount <= 0 || !category) {
                setFormMessage("Enter a valid amount and choose a category before logging.", "is-error");
                return;
            }

            setFormMessage(`Expense of \u20B9${amount.toLocaleString("en-IN")} logged under ${category}.`, "is-success");
            expenseForm.reset();
            amountInput?.focus();
        });

        adviceButton?.addEventListener("click", () => {
            currentInsightIndex = (currentInsightIndex + 1) % coachInsights.length;
            const nextInsight = coachInsights[currentInsightIndex];

            if (insightText) {
                insightText.textContent = nextInsight.text;
            }

            if (adviceMeta) {
                adviceMeta.textContent = nextInsight.meta;
            }

            highlightCard?.classList.remove("is-emphasized");
            window.requestAnimationFrame(() => {
                highlightCard?.classList.add("is-emphasized");
            });
        });
    }

    window.initFinancialPage = initFinancialPage;

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => initFinancialPage(document), { once: true });
    } else {
        initFinancialPage(document);
    }
})();
