(function () {
    /**
     * Senior/Gold Solution:
     * 1. Window darajasida (Capture phase) barcha clicklarni ushlaymiz.
     * 2. Modal ichidagi link bo'lsa, Frappe'ning barcha eventlarini "atom bombasi" bilan portlatamiz.
     * 3. Atributlarni o'chirish orqali Routerni "ko'r" qilamiz.
     */

    const neutralizer = (e) => {
        // Link field dropdownlarini ignore qilish
        if (e.target.closest('.awesomplete') || e.target.closest('.link-field')) {
            return;
        }

        // Modal ichidagi linkni topamiz
        const link = e.target.closest('.modal-body a[data-doctype], .modal-body a[href*="/"]');

        if (link) {
            console.log("Brutal Truth: Intercepting link:", link.innerText);

            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();

            // Linkning navigatsiya atributlarini o'chirib tashlaymiz
            link.removeAttribute('href');
            link.removeAttribute('data-doctype');
            link.removeAttribute('data-name');

            // Select checkbox inside the row
            const row = link.closest('.dt-row, .list-item, .grid-row');
            if (row) {
                const checkbox = row.querySelector('input[type="checkbox"]');
                if (checkbox) {
                    checkbox.click();
                    console.log("Brutal Truth: Checkbox toggled.");
                } else {
                    row.click();
                    console.log("Brutal Truth: Row clicked.");
                }
            }

            return false;
        }
    };

    // 'true' flagi bu Capture phase ekanligini bildiradi.
    window.addEventListener('click', neutralizer, true);
    window.addEventListener('mousedown', neutralizer, true);

    // Vizual qism: Foydalanuvchi linkni link deb o'ylamasligi kerak
    const style = document.createElement('style');
    style.innerHTML = `
        .modal-body a[data-doctype]:not(.awesomplete a):not(.link-field a),
        .modal-body a:not(.awesomplete a):not(.link-field a) {
            color: #212529 !important;
            text-decoration: underline !important;
            cursor: pointer !important;
        }
        .modal-body .dt-row:hover, .modal-body .list-item:hover {
            background-color: #f8f9fa !important;
        }
    `;
    document.head.appendChild(style);

})();
