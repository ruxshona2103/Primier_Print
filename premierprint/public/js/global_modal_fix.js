(function() {
    /**
     * Senior/Gold Solution:
     * 1. Window darajasida (Capture phase) barcha clicklarni ushlaymiz.
     * 2. Modal ichidagi link bo'lsa, Frappe'ning barcha eventlarini "atom bombasi" bilan portlatamiz.
     * 3. Atributlarni o'chirish orqali Routerni "ko'r" qilamiz.
     */

    const neutralizer = (e) => {
        // Modal ichidagi linkni topamiz
        const link = e.target.closest('.modal-body a');

        if (link) {
            // Frappe Routerni to'xtatish uchun eng muhim qadamlar:
            e.preventDefault();
            e.stopImmediatePropagation(); // Boshqa barcha JS'larni (Frappe Router) to'xtatadi
            e.stopPropagation();

            // Linkning navigatsiya atributlarini butunlay o'chirib tashlaymiz
            link.removeAttribute('href');
            link.removeAttribute('data-doctype');
            link.removeAttribute('data-name');
            link.style.pointerEvents = 'none';

            // Checkbox belgilanishi uchun linkning ota-elementiga (qatorga) click beramiz
            const row = link.closest('.dt-row, .list-item');
            if (row) {
                // Infinite loop bo'lmasligi uchun chetdan click beramiz
                row.click();
            }

            console.log("Brutal Truth: Link intercepted and neutralized at window level.");
            return false;
        }
    };

    // 'true' flagi bu Capture phase ekanligini bildiradi.
    // Bu Frappe'ning ichki listenerlaridan oldin bizning kod ishga tushishini kafolatlaydi.
    window.addEventListener('click', neutralizer, true);

    // Vizual qism: Foydalanuvchi linkni link deb o'ylamasligi kerak
    const style = document.createElement('style');
    style.innerHTML = `
        .modal-body a[data-doctype], .modal-body a {
            color: #212529 !important;
            text-decoration: none !important;
            cursor: pointer !important;
            pointer-events: none !important;
        }
        .modal-body .dt-row:hover, .modal-body .list-item:hover {
            background-color: #f8f9fa !important;
        }
    `;
    document.head.appendChild(style);

})();
