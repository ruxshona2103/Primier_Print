/**
 * Stock Entry - Sales Order and Sales Order Item Filters
 * 
 * Key features:
 * 1. Sales Order - custom query showing customer_name
 * 2. Sales Order Item - filtered by Sales Order, link disabled (Child Table)
 */

frappe.ui.form.on('Stock Entry', {
    setup: function (frm) {
        // 1. Sales Order query - show customer name prominently in dropdown
        frm.set_query("custom_sales_order", function () {
            return {
                query: "premierprint.utils.stock_entry.get_sales_order_query",
                filters: {}
            };
        });

        // 2. Sales Order Item query - FILTER by selected Sales Order
        frm.set_query("custom_sales_order_item", function () {
            let so = frm.doc.custom_sales_order;
            if (!so) {
                frappe.show_alert({
                    message: __('Avval Sales Order tanlang'),
                    indicator: 'orange'
                });
                return { filters: { name: ['=', ''] } };
            }
            return {
                query: "premierprint.utils.stock_entry.get_sales_order_items_query",
                filters: {
                    parent: so,
                    sales_order: so
                }
            };
        });
    },

    refresh: function (frm) {
        // DISABLE link navigation for Sales Order Item (it's a Child Table - no page exists)
        disable_link_navigation(frm, 'custom_sales_order_item');
    },

    custom_sales_order: function (frm) {
        // Clear Sales Order Item when Sales Order changes
        if (frm.doc.__islocal || !frm.doc.custom_sales_order) {
            frm.set_value("custom_sales_order_item", "");
        }
        // Re-apply link navigation disable after field changes
        setTimeout(() => disable_link_navigation(frm, 'custom_sales_order_item'), 300);
    },

    custom_sales_order_item: function (frm) {
        // Re-apply after value changes
        setTimeout(() => disable_link_navigation(frm, 'custom_sales_order_item'), 300);
    }
});

/**
 * Disable link navigation for a field (prevents "Page not found" for Child Tables)
 * Uses multiple techniques for reliability:
 * 1. CSS to hide the link arrow button
 * 2. Event handlers to prevent navigation
 * 3. Override open_link method
 */
function disable_link_navigation(frm, fieldname) {
    let field = frm.fields_dict[fieldname];
    if (!field) return;

    // Method 1: Hide link button with CSS (more reliable)
    if (field.$wrapper) {
        field.$wrapper.find('.link-btn').hide();
        // Also add a CSS class to keep it hidden on re-render
        field.$wrapper.addClass('hide-link-btn');
    }

    // Method 2: Prevent click events on link button
    if (field.$input) {
        // Remove any existing handlers and add ours
        field.$wrapper.find('.link-btn').off('click').on('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            frappe.show_alert({
                message: __('Bu ichki jadval maydoni - alohida sahifa mavjud emas'),
                indicator: 'orange'
            });
            return false;
        });
    }

    // Method 3: Override the open_link method if it exists
    if (field.open_link) {
        field.open_link = function () {
            frappe.show_alert({
                message: __('Sales Order Item - bu Child Table. Item Code ustiga bosing.'),
                indicator: 'orange'
            });
        };
    }
}

// Add CSS to ensure link button stays hidden
$(document).ready(function () {
    $('<style>')
        .prop('type', 'text/css')
        .html('.hide-link-btn .link-btn { display: none !important; }')
        .appendTo('head');
});
