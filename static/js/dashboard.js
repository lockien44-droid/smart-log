let isPaused = false;
let realtimeOrders = {};
let realtimeWarehouses = {};
let renderTimer = null;
let alertSnapshotInitialized = false;
const knownAlerts = new Set();
let appliedInventoryFilters = {
    query: "",
    warehouse: "",
    level: ""
};
let stockAlertsEnabled =
    localStorage.getItem("stockAlertsEnabled") !== "false";
let pushNotificationFilter = "ALL";
let currentNotificationAlerts = [];
let warehouseSortMode = "latest";
let selectedOrderDetailId = null;
const readNotificationKeys = new Set(
    JSON.parse(localStorage.getItem("readNotificationKeys") || "[]")
);

const dashboardNav = document.getElementById("dashboardNav");
const inventoryNav = document.getElementById("inventoryNav");
const orderDetailsNav = document.getElementById("orderDetailsNav");
const breadcrumbCurrent = document.getElementById("breadcrumbCurrent");
const breadcrumbPath = document.getElementById("breadcrumbPath");
const overviewView = document.getElementById("overviewView");
const inventoryView = document.getElementById("inventoryView");
const orderDetailsView = document.getElementById("orderDetailsView");
const orderManagementNav = document.getElementById("orderManagementNav");
const forecastNav = document.getElementById("forecastNav");
const productMenuToggle = document.getElementById("productMenuToggle");
const productSubmenu = document.getElementById("productSubmenu");
const allProductsNav = document.getElementById("allProductsNav");
const addProductNav = document.getElementById("addProductNav");
const restockNav = document.getElementById("restockNav");
const alertNav = document.getElementById("alertNav");
const historyNav = document.getElementById("historyNav");

function setBreadcrumb(path) {
    const home = "Trang chủ";
    const parts = Array.isArray(path) ? path : [home, path];
    const normalizedParts =
        parts.length === 1 || parts[parts.length - 1] === home
            ? [home]
            : parts;

    if (!breadcrumbPath) return;
    breadcrumbPath.innerHTML = '<span class="breadcrumb-logo">S</span>';
    normalizedParts.forEach((part, index) => {
        if (index > 0) {
            const separator = document.createElement("span");
            separator.className = "breadcrumb-separator";
            separator.textContent = ">";
            breadcrumbPath.appendChild(separator);
        }
        const item = document.createElement("span");
        item.className = "breadcrumb-link";
        item.textContent = part;
        breadcrumbPath.appendChild(item);
    });
}

function showMenuView(activeNav, activeView) {
    [overviewView, inventoryView, orderDetailsView].forEach(view =>
        view.classList.add("view-hidden")
    );
    [dashboardNav, inventoryNav, orderDetailsNav].forEach(nav =>
        nav.classList.remove("active")
    );
    activeView.classList.remove("view-hidden");
    activeNav.classList.add("active");
}

dashboardNav.addEventListener("click", () => {
    [dashboardNav, inventoryNav, orderDetailsNav].forEach(nav =>
        nav.classList.remove("active")
    );
    showDashboardPage();
    dashboardNav.classList.add("active");
    setBreadcrumb(["Trang chủ"]);
    window.scrollTo({ top: 0, behavior: "smooth" });
});

const featureSectionIds = [
    "overviewSection",
    "inventoryOverviewSection",
    "orderFormSection",
    "salesAnalysisSection",
    "displayServiceSection",
    "modelSection",
    "chartsSection",
    "realtimeLogSection",
    "addProductSection",
    "restockSection",
    "alertsSection",
    "orderListSection",
    "warehouseInventorySection"
];

const dashboardSectionIds = [
    "overviewSection",
    "salesAnalysisSection",
    "displayServiceSection"
];

function showMainDashboard() {
    overviewView.classList.remove("view-hidden");
    inventoryView.classList.remove("view-hidden");
    orderDetailsView.classList.add("view-hidden");
}

function showSections(sectionIds) {
    showMainDashboard();
    featureSectionIds.forEach(id => {
        document.getElementById(id)?.classList.add("feature-hidden");
    });
    sectionIds.forEach(id => {
        document.getElementById(id)?.classList.remove("feature-hidden");
    });
}

function showDashboardPage() {
    showSections(dashboardSectionIds);
}

function activateMenu(element, breadcrumb, sectionIds) {
    document.querySelectorAll(
        ".sidebar .nav-item.active, .sidebar .menu-parent.active"
    ).forEach(item => item.classList.remove("active"));
    element.classList.add("active");
    const sections = Array.isArray(sectionIds) ? sectionIds : [sectionIds];
    showSections(sections);
    setBreadcrumb(breadcrumb);
    window.scrollTo({ top: 0, behavior: "smooth" });
}

window.openAlertNotification = orderId => {
    activateMenu(alertNav, ["Trang chủ", "Cảnh báo tồn kho"], "alertsSection");
    document.getElementById("pushWrapper").classList.remove("open");

    setTimeout(() => {
        const targetRow = Array.from(
            document.querySelectorAll("#alertsPageBody tr[data-order-id]")
        ).find(row => row.dataset.orderId === String(orderId));
        if (!targetRow) {
            document.getElementById("alertsSection")?.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
            return;
        }
        targetRow.classList.add("alert-row-highlight");
        targetRow.scrollIntoView({ behavior: "smooth", block: "center" });
        setTimeout(() => targetRow.classList.remove("alert-row-highlight"), 3000);
    }, 400);
    return false;
};

orderManagementNav.addEventListener("click", () => {
    activateMenu(orderManagementNav, ["Trang chủ", "Quản lý đơn hàng"], ["orderFormSection", "orderListSection"]);
});

forecastNav.addEventListener("click", () => {
    activateMenu(forecastNav, ["Trang chủ", "Dự báo nhu cầu"], ["modelSection", "chartsSection"]);
});

productMenuToggle.addEventListener("click", () => {
    productSubmenu.classList.toggle("collapsed");
    productMenuToggle.querySelector(".chevron").textContent = productSubmenu.classList.contains("collapsed") ? ">" : "v";
});

allProductsNav.addEventListener("click", () => {
    activateMenu(allProductsNav, ["Trang chủ", "Quản lý sản phẩm", "Tất cả sản phẩm"], "warehouseInventorySection");
});

addProductNav.addEventListener("click", () => {
    activateMenu(addProductNav, ["Trang chủ", "Quản lý sản phẩm", "Thêm / Nhập hàng"], ["addProductSection", "restockSection"]);
    document.getElementById("newProductId").focus();
});

restockNav?.addEventListener("click", () => {
    activateMenu(restockNav, ["Trang chủ", "Quản lý sản phẩm", "Thêm / Nhập hàng"], "restockSection");
    document.getElementById("restockProductId").focus();
});

alertNav.addEventListener("click", event => {
    event.stopPropagation();
    activateMenu(alertNav, ["Trang chủ", "Cảnh báo tồn kho"], "alertsSection");
    document.getElementById("pushWrapper").classList.remove("open");
});

historyNav.addEventListener("click", () => {
    activateMenu(historyNav, ["Trang chủ", "Lịch sử đồng bộ"], "realtimeLogSection");
});

inventoryNav.addEventListener("click", () => {
    activateMenu(inventoryNav, ["Trang chủ", "Quản lý sản phẩm", "Quản lý tồn kho"], ["inventoryOverviewSection", "orderListSection", "warehouseInventorySection"]);
});

orderDetailsNav.addEventListener("click", () => {
    showOrderDetailsList();
});

document.getElementById("pushNotificationIcon").addEventListener("click", event => {
    event.stopPropagation();
    document.getElementById("pushWrapper").classList.toggle("open");
});

document.getElementById("pushDropdownList").addEventListener("click", event => {
    const item = event.target.closest(".push-dropdown-item");
    if (!item) return;

    event.preventDefault();
    event.stopPropagation();
    markNotificationRead(item.dataset.notificationKey);
    if (event.target.closest('[data-action="mark-read"]')) {
        renderPushDropdown(currentNotificationAlerts);
        return;
    }
    const orderId = item.dataset.orderId || "";
    window.openAlertNotification(orderId);
});

document.getElementById("viewAllAlertsBtn").addEventListener("click", event => {
    event.preventDefault();
    event.stopPropagation();
    activateMenu(alertNav, "Cảnh báo tồn kho", "alertsSection");
    document.getElementById("pushWrapper").classList.remove("open");
});

document.getElementById("markAllReadBtn").addEventListener("click", event => {
    event.preventDefault();
    event.stopPropagation();
    currentNotificationAlerts.forEach(order =>
        readNotificationKeys.add(alertKey(order))
    );
    saveReadNotificationKeys();
    renderPushDropdown(currentNotificationAlerts);
});

document.getElementById("pushFilterTabs").addEventListener("click", event => {
    const tab = event.target.closest(".push-filter-tab");
    if (!tab) return;
    event.stopPropagation();
    pushNotificationFilter = tab.dataset.filter;
    document.querySelectorAll(".push-filter-tab").forEach(button =>
        button.classList.toggle("active", button === tab)
    );
    renderPushDropdown(currentNotificationAlerts);
});

document.addEventListener("click", () => {
    document.getElementById("pushWrapper").classList.remove("open");
});

function applyInventoryFilters() {
    appliedInventoryFilters = {
        query: document.getElementById("searchInput").value
            .trim().toLowerCase(),
        warehouse: document.getElementById("warehouseFilter").value,
        level: document.getElementById("levelFilter").value
    };
    scheduleRender();
}

document.getElementById("inventorySearchBtn").addEventListener(
    "click",
    applyInventoryFilters
);
document.getElementById("searchInput").addEventListener("keydown", event => {
    if (event.key === "Enter") applyInventoryFilters();
});
document.getElementById("searchInput").addEventListener("input", event => {
    if (event.target.value !== "") return;
    document.getElementById("warehouseFilter").value = "";
    document.getElementById("levelFilter").value = "";
    appliedInventoryFilters = { query: "", warehouse: "", level: "" };
    document.querySelectorAll(".inventory-tab").forEach(button =>
        button.classList.toggle("active", button.dataset.level === "")
    );
    scheduleRender();
});

document.querySelectorAll(".inventory-tab").forEach(tabButton => {
    tabButton.addEventListener("click", () => {
        document.querySelectorAll(".inventory-tab").forEach(button =>
            button.classList.remove("active")
        );
        tabButton.classList.add("active");
        document.getElementById("levelFilter").value =
            tabButton.dataset.level || "";
        appliedInventoryFilters.level = tabButton.dataset.level || "";
        scheduleRender();
    });
});

function updateStockAlertToggle() {
    document.getElementById("stockAlertSwitch").classList.toggle(
        "off",
        !stockAlertsEnabled
    );
    document.getElementById("stockAlertToggle").title =
        stockAlertsEnabled
            ? "Đang bật thông báo sắp hết hàng"
            : "ang tt thng bo sp ht hng";
}

function toggleStockAlerts() {
    stockAlertsEnabled = !stockAlertsEnabled;
    localStorage.setItem("stockAlertsEnabled", String(stockAlertsEnabled));
    updateStockAlertToggle();
    scheduleRender();
    if (!stockAlertsEnabled) {
        document.getElementById("toastContainer").innerHTML = "";
        document.getElementById("pushWrapper").classList.remove("open");
    }
}

document.getElementById("stockAlertToggle").addEventListener(
    "click",
    toggleStockAlerts
);
document.getElementById("stockAlertToggle").addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggleStockAlerts();
    }
});
updateStockAlertToggle();

function scheduleRender() {
    if (renderTimer) return;

    renderTimer = setTimeout(() => {
        renderTimer = null;
        renderDashboard(realtimeOrders);
    }, 250);
}

let latestFirebaseOrders = {};

window.applyFirebaseOrders = data => {
    latestFirebaseOrders = data || {};
    if (isPaused) return;

    detectNewAlerts(latestFirebaseOrders);
    realtimeOrders = latestFirebaseOrders;
    scheduleRender();
    renderStockLevelChart(Object.values(latestFirebaseOrders));
    renderLatestRealtimeLog(Object.values(latestFirebaseOrders));
    renderAlertsPage(Object.values(latestFirebaseOrders));
    const syncTime = new Date().toLocaleTimeString("vi-VN");
    ["lastSyncTime", "inventoryLastSyncTime"].forEach(id => {
        const element = document.getElementById(id);
        if (element) element.textContent = syncTime;
    });
    ["firebaseConnection", "inventoryFirebaseConnection"].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = "Connected";
            element.className = "firebase-connected";
        }
    });
    document.getElementById("realtimeStatus").innerHTML =
        " Đang đồng bộ trực tiếp qua Firebase onValue";
};

function renderAlertsPage(orders) {
    const alerts = orders
        .filter(isWarningOrder)
        .sort((a, b) =>
            Number(b.last_updated || 0) - Number(a.last_updated || 0)
        );
    const body = document.getElementById("alertsPageBody");
    body.innerHTML = alerts.length
        ? alerts.map(order => `
            <tr data-order-id="${order.order_id || ""}">
                <td>${order.order_id || "-"}</td>
                <td>${order.warehouse_id || "-"}</td>
                <td>${order.product_id || "-"}</td>
                <td>${order.inventory ?? 0}</td>
                <td>${order.future_demand ?? 0}</td>
                <td><span class="level-badge level-${order.inventory_level}">${order.inventory_level}</span></td>
                <td>${order.reorder_quantity ?? 0}</td>
                <td>${order.last_updated_text || "-"}</td>
            </tr>
        `).join("")
        : '<tr><td colspan="8">Không có cảnh báo tồn kho.</td></tr>';
}

window.handleFirebaseError = error => {
    console.error("Firebase onValue failed:", error);
    document.getElementById("realtimeStatus").innerHTML =
        '<span style="color:#ef4444"> Firebase mt kt ni</span>';
    ["firebaseConnection", "inventoryFirebaseConnection"].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = "Disconnected";
            element.className = "firebase-error";
        }
    });
};

window.applyFirebaseWarehouses = data => {
    realtimeWarehouses = data || {};
    renderWarehouseInventory(realtimeWarehouses);
    renderStockForecastChart(realtimeWarehouses);
    renderSalesAnalysis(Object.values(realtimeOrders || {}), realtimeWarehouses);
    renderOrderWarehouseOptions(realtimeWarehouses);
    renderRestockWarehouseOptions(realtimeWarehouses);
};

function renderStockLevelChart(orders) {
    const levels = {
        NORMAL: 0,
        LOW: 0,
        CRITICAL: 0,
        OUT_OF_STOCK: 0
    };
    orders.forEach(order => {
        const level = order.inventory_level || "NORMAL";
        if (levels[level] !== undefined) levels[level]++;
    });
    const max = Math.max(1, ...Object.values(levels));
    const colors = {
        NORMAL: "#22c55e",
        LOW: "#eab308",
        CRITICAL: "#f97316",
        OUT_OF_STOCK: "#ef4444"
    };
    document.getElementById("stockLevelChart").innerHTML =
        Object.entries(levels).map(([level, count]) => `
            <div class="visual-row">
                <span>${level}</span>
                <div class="visual-track">
                    <div class="visual-fill" style="width:${count / max * 100}%;background:${colors[level]}"></div>
                </div>
                <strong>${count}</strong>
            </div>
        `).join("");
}

function flattenWarehouseProducts(data) {
    const rows = [];
    Object.entries(data || {}).forEach(([warehouseId, warehouse]) => {
        Object.entries(warehouse?.products || {}).forEach(([productId, product]) => {
            rows.push({ warehouseId, productId, ...product });
        });
    });
    return rows;
}

function renderRestockWarehouseOptions(data) {
    const warehouseSelect = document.getElementById("restockWarehouse");
    const productSelect = document.getElementById("restockProductId");
    if (!warehouseSelect || !productSelect) return;

    const currentWarehouse = warehouseSelect.value;
    const warehouses = Object.keys(data || {}).sort((a, b) =>
        String(a).localeCompare(String(b), "vi", { numeric: true })
    );

    warehouseSelect.innerHTML = warehouses.length
        ? '<option value="">Chọn kho</option>' + warehouses.map(warehouse =>
            `<option value="${escapeAttribute(warehouse)}">${warehouse}</option>`
        ).join("")
        : '<option value="">Chưa có kho</option>';

    if (warehouses.includes(currentWarehouse)) {
        warehouseSelect.value = currentWarehouse;
    } else if (warehouses.length) {
        warehouseSelect.value = warehouses[0];
    }

    renderRestockProductOptions();
}

function renderOrderWarehouseOptions(data) {
    const warehouseSelect = document.getElementById("formWarehouseId");
    const productSelect = document.getElementById("formProductId");
    if (!warehouseSelect || !productSelect) return;

    const currentWarehouse = warehouseSelect.value;
    const warehouses = Object.keys(data || {}).sort((a, b) =>
        String(a).localeCompare(String(b), "vi", { numeric: true })
    );

    warehouseSelect.innerHTML = warehouses.length
        ? '<option value="">Chọn kho</option>' + warehouses.map(warehouse =>
            `<option value="${escapeAttribute(warehouse)}">${warehouse}</option>`
        ).join("")
        : '<option value="">Chưa có kho</option>';

    if (warehouses.includes(currentWarehouse)) {
        warehouseSelect.value = currentWarehouse;
    } else if (warehouses.length) {
        warehouseSelect.value = warehouses[0];
    }

    renderOrderProductOptions();
}

function renderOrderProductOptions() {
    const warehouseSelect = document.getElementById("formWarehouseId");
    const productSelect = document.getElementById("formProductId");
    if (!warehouseSelect || !productSelect) return;

    const warehouseId = warehouseSelect.value;
    const currentProduct = productSelect.value;
    const products = Object.keys(
        realtimeWarehouses?.[warehouseId]?.products || {}
    ).sort((a, b) => String(a).localeCompare(String(b), "vi", { numeric: true }));

    productSelect.innerHTML = products.length
        ? '<option value="">Chọn sản phẩm</option>' + products.map(product =>
            `<option value="${escapeAttribute(product)}">${product}</option>`
        ).join("")
        : '<option value="">Kho này chưa có sản phẩm</option>';

    if (products.includes(currentProduct)) {
        productSelect.value = currentProduct;
    } else if (products.length) {
        productSelect.value = products[0];
    }
}

function renderRestockProductOptions() {
    const warehouseSelect = document.getElementById("restockWarehouse");
    const productSelect = document.getElementById("restockProductId");
    if (!warehouseSelect || !productSelect) return;

    const warehouseId = warehouseSelect.value;
    const currentProduct = productSelect.value;
    const products = Object.keys(
        realtimeWarehouses?.[warehouseId]?.products || {}
    ).sort((a, b) => String(a).localeCompare(String(b), "vi", { numeric: true }));

    productSelect.innerHTML = products.length
        ? '<option value="">Chọn sản phẩm / SKU</option>' + products.map(product =>
            `<option value="${escapeAttribute(product)}">${product}</option>`
        ).join("")
        : '<option value="">Kho này chưa có SKU</option>';

    if (products.includes(currentProduct)) {
        productSelect.value = currentProduct;
    } else if (products.length) {
        productSelect.value = products[0];
    }
}

function toNumber(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function escapeAttribute(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

function forecast30From7(value) {
    return Math.max(0, Math.round(toNumber(value) * 30 / 7));
}

function sales7Days(item) {
    if (item.sales_7_days != null) return toNumber(item.sales_7_days);
    if (item.sales_last_7_days != null) return toNumber(item.sales_last_7_days);
    if (item.sales_mean_7 != null) return Math.round(toNumber(item.sales_mean_7) * 7);
    if (item.daily_sales != null) return Math.round(toNumber(item.daily_sales) * 7);
    if (item.future_demand != null) return toNumber(item.future_demand);
    return 0;
}

function sales30Days(item) {
    if (item.sales_30_days != null) return toNumber(item.sales_30_days);
    if (item.sales_last_30_days != null) return toNumber(item.sales_last_30_days);
    if (item.sales_mean_30 != null) return Math.round(toNumber(item.sales_mean_30) * 30);
    if (item.daily_sales != null) return Math.round(toNumber(item.daily_sales) * 30);
    if (item.future_demand_30 != null) return toNumber(item.future_demand_30);
    if (item.future_demand != null) return forecast30From7(item.future_demand);
    return 0;
}

function renderSalesAnalysis(orders = [], warehouses = {}) {
    const rows = flattenWarehouseProducts(warehouses);
    const warehouseIds = new Set();
    const productIds = new Set();

    if (rows.length) {
        rows.forEach(item => {
            if (item.warehouseId) warehouseIds.add(item.warehouseId);
            if (item.productId) productIds.add(item.productId);
        });
    } else {
        orders.forEach(order => {
            if (order.warehouse_id) warehouseIds.add(order.warehouse_id);
            if (order.product_id) productIds.add(order.product_id);
        });
    }

    const sourceRows = rows.length
        ? rows
        : orders.map(order => ({
            sales_7_days: order.sales_7_days,
            sales_30_days: order.sales_30_days,
            daily_sales: order.daily_sales,
            future_demand: order.future_demand,
            future_demand_30: order.future_demand_30
        }));

    const totalSales7 = sourceRows.reduce(
        (sum, item) => sum + sales7Days(item),
        0
    );
    const totalSales30 = sourceRows.reduce(
        (sum, item) => sum + sales30Days(item),
        0
    );

    const setText = (id, value) => {
        const element = document.getElementById(id);
        if (element) element.innerText = Number(value || 0).toLocaleString("vi-VN");
    };

    setText("salesWarehouseTotal", warehouseIds.size);
    setText("salesProductTotal", productIds.size);
    setText("sales7DaysTotal", totalSales7);
    setText("sales30DaysTotal", totalSales30);
}

function renderStockForecastChart(data) {
    const rows = flattenWarehouseProducts(data)
        .sort((a, b) => Number(b.last_updated || 0) - Number(a.last_updated || 0))
        .slice(0, 10);
    const max = Math.max(
        1,
        ...rows.flatMap(item => [
            Number(item.stock || 0),
            Number(item.future_demand || 0)
        ])
    );
    document.getElementById("stockForecastChart").innerHTML = rows.length
        ? rows.map(item => `
            <div>
                <div style="font-size:12px;font-weight:700;margin-bottom:3px">${item.warehouseId} / ${item.productId}</div>
                <div class="visual-row">
                    <span>Tồn kho</span><div class="visual-track"><div class="visual-fill" style="width:${Number(item.stock || 0) / max * 100}%"></div></div><strong>${item.stock || 0}</strong>
                </div>
                <div class="visual-row">
                    <span>Dự báo RF</span><div class="visual-track"><div class="visual-fill demand" style="width:${Number(item.future_demand || 0) / max * 100}%"></div></div><strong>${item.future_demand || 0}</strong>
                </div>
            </div>
        `).join("")
        : '<div>Chưa có dữ liệu sản phẩm.</div>';
}

function renderLatestRealtimeLog(orders) {
    const container = document.getElementById("realtimeLog");
    if (!container) return;

    const latestOrders = [...orders]
        .sort((a, b) => Number(b.last_updated || 0) - Number(a.last_updated || 0))
        .slice(0, 10);

    if (!latestOrders.length) {
        container.innerHTML =
            '<div class="log-line">Đang chờ dữ liệu đơn hàng realtime...</div>';
        return;
    }

    container.innerHTML = "";
    latestOrders.forEach(order => {
        const time = order.last_updated_text
            ? String(order.last_updated_text).split(" ")[0]
            : new Date(
                  Number(order.last_updated || order.timestamp || Date.now()) *
                      (Number(order.last_updated || order.timestamp || 0) < 1000000000000 ? 1000 : 1)
              ).toLocaleTimeString("vi-VN");
        const line = document.createElement("div");
        line.className = "log-line";
        line.textContent =
            `${time} - ${order.order_id || "N/A"} | ${order.status || "N/A"} | ` +
            `Kho ${order.warehouse_id || "N/A"} / ${order.product_id || "N/A"} | ` +
            `Tồn ${order.inventory ?? "-"} | Dự báo ${order.future_demand ?? "-"} | ` +
            `Cảnh báo ${order.alert || order.inventory_level || "NORMAL"}`;
        container.appendChild(line);
    });
}

function renderWarehouseInventory(data) {
    const tableBody = document.getElementById("warehouseTableBody");
    const rows = flattenWarehouseProducts(data);

    if (warehouseSortMode === "warehouse") {
        rows.sort((a, b) => {
            const warehouseCompare = String(a.warehouseId).localeCompare(
                String(b.warehouseId),
                "vi",
                { numeric: true }
            );
            if (warehouseCompare !== 0) return warehouseCompare;
            return String(a.productId).localeCompare(
                String(b.productId),
                "vi",
                { numeric: true }
            );
        });
    } else {
        rows.sort((a, b) =>
            Number(b.last_updated || 0) - Number(a.last_updated || 0)
        );
    }

    tableBody.innerHTML = rows.length
        ? rows.map(item => {
            const forecast7 = toNumber(item.future_demand, 0);
            const forecast30 = item.future_demand_30 != null
                ? toNumber(item.future_demand_30, 0)
                : forecast30From7(forecast7);
            return `
            <tr>
                <td>${item.warehouseId}</td>
                <td>${item.productId}</td>
                <td><strong>${item.stock ?? 0}</strong></td>
                <td>${sales7Days(item)}</td>
                <td>${sales30Days(item)}</td>
                <td>${forecast7}</td>
                <td>${forecast30}</td>
                <td>${item.reorder_point ?? '-'}</td>
                <td>${item.reorder_quantity ?? 0}</td>
                <td>
                    <span class="level-badge level-${item.inventory_level || 'NORMAL'}">
                        ${item.inventory_level || 'CHƯA ĐÁNH GIÁ'}
                    </span>
                </td>
                <td>
                    <button
                        class="table-edit-btn"
                        type="button"
                        data-action="edit-product"
                        data-warehouse="${escapeAttribute(item.warehouseId)}"
                        data-product="${escapeAttribute(item.productId)}"
                    >Sửa</button>
                </td>
            </tr>
        `}).join("")
        : '<tr><td colspan="11">Chưa có dữ liệu tồn kho.</td></tr>';
}

document.getElementById("warehouseSortBtn")?.addEventListener("click", () => {
    warehouseSortMode = warehouseSortMode === "latest" ? "warehouse" : "latest";
    const button = document.getElementById("warehouseSortBtn");
    if (button) {
        button.textContent = warehouseSortMode === "warehouse"
            ? "Đang sắp xếp theo kho A→Z"
            : "Sắp xếp kho hàng";
    }
    renderWarehouseInventory(realtimeWarehouses);
});

document.getElementById("restockWarehouse")?.addEventListener("change", () => {
    renderRestockProductOptions();
});

document.getElementById("formWarehouseId")?.addEventListener("change", () => {
    renderOrderProductOptions();
});

document.getElementById("orderTableBody")?.addEventListener("click", event => {
    const row = event.target.closest("tr[data-order-id]");
    if (!row) return;
    openOrderDetail(row.dataset.orderId);
});

document.getElementById("orderTableBody")?.addEventListener("keydown", event => {
    if (event.key !== "Enter") return;
    const row = event.target.closest("tr[data-order-id]");
    if (!row) return;
    openOrderDetail(row.dataset.orderId);
});

document.getElementById("orders")?.addEventListener("click", event => {
    const backButton = event.target.closest('[data-action="back-order-list"]');
    if (backButton) {
        showOrderDetailsList();
        return;
    }

    const item = event.target.closest("[data-order-id]");
    if (!item) return;
    openOrderDetail(item.dataset.orderId);
});

document.addEventListener("click", async event => {
    const editButton = event.target.closest('[data-action="edit-product"]');
    if (!editButton) return;

    const oldWarehouseId = editButton.dataset.warehouse || "";
    const oldProductId = editButton.dataset.product || "";
    const newWarehouseId = prompt("Nhập mã kho mới:", oldWarehouseId);
    if (newWarehouseId === null) return;
    const newProductId = prompt("Nhập tên/mã sản phẩm mới:", oldProductId);
    if (newProductId === null) return;

    const warehouseValue = newWarehouseId.trim();
    const productValue = newProductId.trim();
    if (!warehouseValue || !productValue) {
        alert("Mã kho và tên sản phẩm không được để trống.");
        return;
    }

    editButton.disabled = true;
    editButton.textContent = "Đang sửa...";
    try {
        const response = await fetch("/api/products/rename", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                old_warehouse_id: oldWarehouseId,
                old_product_id: oldProductId,
                new_warehouse_id: warehouseValue,
                new_product_id: productValue
            })
        });
        const result = await response.json();
        if (!response.ok || !result.ok) {
            throw new Error(result.error || "Sửa thông tin kho/sản phẩm thất bại.");
        }
        showToast({
            alert: "UPDATED",
            order_id: productValue,
            warehouse_id: warehouseValue,
            inventory: 0,
            reorder_quantity: 0
        });
    } catch (error) {
        alert(error.message);
    } finally {
        editButton.disabled = false;
        editButton.textContent = "Sửa";
    }
});

function isWarningOrder(order) {
    const alert = String(order?.alert || "NORMAL");
    const level = String(order?.inventory_level || "NORMAL");
    const warningAlerts = new Set([
        "LOW_STOCK",
        "REORDER_REQUIRED",
        "OUT_OF_STOCK",
        "INSUFFICIENT_STOCK"
    ]);
    return (
        warningAlerts.has(alert) ||
        level === "LOW" ||
        level === "CRITICAL" ||
        level === "OUT_OF_STOCK"
    );
}

function alertKey(order) {
    return [
        order.order_id || "",
        order.warehouse_id || "",
        order.product_id || "",
        order.alert || "",
        order.inventory_level || "",
        order.inventory ?? "",
        order.reorder_quantity ?? ""
    ].join("|");
}

function detectNewAlerts(data) {
    const warningOrders = Object.values(data).filter(isWarningOrder);

    if (!alertSnapshotInitialized) {
        warningOrders.forEach(order => knownAlerts.add(alertKey(order)));
        alertSnapshotInitialized = true;
        return;
    }

    if (!stockAlertsEnabled) return;

    warningOrders.forEach(order => {
        const key = alertKey(order);
        if (knownAlerts.has(key)) return;
        knownAlerts.add(key);
        showAlertToast(order);
    });
}

function showAlertToast(order) {
    const container = document.getElementById("toastContainer");
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.innerHTML = `
        <strong> ${order.alert || order.inventory_level}</strong><br>
        ${order.order_id || "N/A"}  Kho ${order.warehouse_id || "N/A"} 
        Tồn ${order.inventory ?? 0}  Cần nhập ${order.reorder_quantity ?? 0}
    `;
    container.prepend(toast);
    while (container.children.length > 3) {
        container.lastElementChild.remove();
    }
    setTimeout(() => toast.remove(), 6000);
}

function renderNotifications(orders, toTimestamp) {
    const alerts = stockAlertsEnabled ? orders
        .filter(isWarningOrder)
        .sort((a, b) =>
            toTimestamp(b.last_updated || b.timestamp) -
            toTimestamp(a.last_updated || a.timestamp)
        ) : [];

    currentNotificationAlerts = alerts;
    const unreadCount = alerts.filter(order =>
        !readNotificationKeys.has(alertKey(order))
    ).length;
    document.getElementById("pushNotificationBadge").textContent =
        unreadCount > 99 ? "99+" : unreadCount;
    document.getElementById("pushNotificationIcon").classList.toggle(
        "push-active",
        unreadCount > 0
    );
    renderPushDropdown(alerts);
}

function saveReadNotificationKeys() {
    localStorage.setItem(
        "readNotificationKeys",
        JSON.stringify(Array.from(readNotificationKeys).slice(-500))
    );
}

function markNotificationRead(key) {
    if (!key) return;
    readNotificationKeys.add(key);
    saveReadNotificationKeys();
}

function notificationTime(order) {
    let value = Number(order.last_updated || order.timestamp || 0);
    if (!value) return order.last_updated_text || "Không rõ thời gian";
    if (value < 1000000000000) value *= 1000;
    const diffSeconds = Math.max(0, Math.floor((Date.now() - value) / 1000));
    if (diffSeconds < 60) return "Va xong";
    if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)} pht trc`;
    if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)} gi trc`;
    return new Date(value).toLocaleString("vi-VN");
}

function renderPushDropdown(alerts) {
    const dropdownList = document.getElementById("pushDropdownList");
    const filteredAlerts = alerts.filter(order => {
        const level = order.inventory_level || "NORMAL";
        if (pushNotificationFilter === "ALL") return true;
        if (pushNotificationFilter === "READ") {
            return readNotificationKeys.has(alertKey(order));
        }
        return level === pushNotificationFilter;
    });

    if (!filteredAlerts.length) {
        dropdownList.innerHTML = '<div class="push-empty">Không có thông báo phù hợp.</div>';
        return;
    }

    dropdownList.innerHTML = filteredAlerts.slice(0, 15).map(order => {
        const level = order.inventory_level || "NORMAL";
        const key = alertKey(order);
        const isUnread = !readNotificationKeys.has(key);
        const title = level === "OUT_OF_STOCK"
            ? " SẢN PHẨM ĐÃ HẾT HÀNG"
            : level === "CRITICAL"
                ? " CẢNH BÁO TỒN KHO NGUY CẤP"
                : level === "LOW"
                    ? " SẢN PHẨM SẮP HẾT HÀNG"
                    : " TỒN KHO BÌNH THƯỜNG";
        return `
            <div class="push-dropdown-item level-${level} ${isUnread ? "unread" : ""}"
               href="#alertsSection"
               data-order-id="${order.order_id || ""}"
               data-notification-key="${key}">
                ${isUnread ? '<span class="push-unread-dot"></span>' : ""}
                <div class="push-dropdown-icon">S</div>
                <div>
                    <div class="push-title-row">
                        <strong>${title}</strong>
                        <span class="push-level-badge">${level.replaceAll("_", " ")}</span>
                    </div>
                    <p>
                        M: ${order.order_id || "N/A"} | Kho: ${order.warehouse_id || "N/A"}<br>
                        Tồn: ${order.inventory ?? 0} | Dự báo RF: ${order.future_demand ?? 0} |
                        Cần nhập: ${order.reorder_quantity ?? 0}
                    </p>
                    <span class="push-notification-time">${notificationTime(order)}</span>
                    <div class="push-item-actions">
                        <button class="push-item-action" data-action="view">Xem chi tit</button>
                        ${isUnread ? '<button class="push-item-action" data-action="mark-read">Đánh dấu đã đọc</button>' : ""}
                    </div>
                </div>
            </div>
        `;
    }).join("");

    const unreadCount = alerts.filter(order =>
        !readNotificationKeys.has(alertKey(order))
    ).length;
    document.getElementById("pushNotificationBadge").textContent =
        unreadCount > 99 ? "99+" : unreadCount;
    document.getElementById("pushNotificationIcon").classList.toggle(
        "push-active",
        unreadCount > 0
    );
}

// Nt Tm Dng
document.getElementById('pauseBtn').addEventListener('click', () => {
    isPaused = !isPaused;
    const btn = document.getElementById('pauseBtn');
    const status = document.getElementById('realtimeStatus');
    
    if (isPaused) {
        btn.textContent = ' Tip tc';
        btn.style.background = '#22c55e';
        status.innerHTML = ' <span style="color:#f59e0b"> tm dng</span>';
    } else {
        btn.textContent = ' Tm dng';
        btn.style.background = '#f59e0b';
        status.innerHTML = ' Đang đồng bộ trực tiếp qua Firebase onValue';
        window.applyFirebaseOrders(latestFirebaseOrders);
    }
});

function renderDashboard(data) {
    const ordersDiv = document.getElementById("orders");
    const tableBody = document.getElementById("orderTableBody");
    const setText = (id, value) => {
        const element = document.getElementById(id);
        if (element) element.innerText = value;
    };

    ordersDiv.innerHTML = "";
    tableBody.innerHTML = "";

    let totalOrders = 0, normalStock = 0, lowStock = 0;
    let criticalStock = 0, outOfStock = 0, reorder = 0, totalInv = 0;
    const orderStatusCounts = {
        Pending: 0,
        Processing: 0,
        Shipping: 0,
        Delivered: 0,
        Cancelled: 0
    };

    const toTimestamp = value => {
        if (typeof value === "number") return value;
        const numeric = Number(value);
        if (Number.isFinite(numeric)) return numeric;
        const parsed = Date.parse(value);
        return Number.isFinite(parsed) ? parsed : 0;
    };

    const allOrders = Object.values(data);
    const latestTimestamp = allOrders.reduce((latest, order) => {
        return Math.max(
            latest,
            toTimestamp(order.last_updated || order.timestamp)
        );
    }, 0);
    document.getElementById("latestDataTime").textContent =
        latestTimestamp
            ? new Date(
                latestTimestamp < 1000000000000
                    ? latestTimestamp * 1000
                    : latestTimestamp
              ).toLocaleString("vi-VN")
            : "Chưa có";
    const inventoryLatestElement = document.getElementById("inventoryLatestDataTime");
    if (inventoryLatestElement) {
        inventoryLatestElement.textContent = document.getElementById("latestDataTime").textContent;
    }
    const warehouseFilter = document.getElementById("warehouseFilter");
    const currentWarehouse = warehouseFilter.value;
    const warehouses = [...new Set(
        allOrders.map(order => order.warehouse_id).filter(Boolean)
    )].sort();
    warehouseFilter.innerHTML =
        '<option value="">Tt c kho</option>' +
        warehouses.map(warehouse =>
            `<option value="${warehouse}">${warehouse}</option>`
        ).join("");
    warehouseFilter.value = warehouses.includes(currentWarehouse)
        ? currentWarehouse
        : "";

    const query = appliedInventoryFilters.query;
    const selectedWarehouse = appliedInventoryFilters.warehouse;
    const selectedLevel = appliedInventoryFilters.level;

    const filteredOrders = allOrders.filter(order => {
        const searchable = [
            order.order_id,
            order.product_id,
            order.warehouse_id
        ].join(" ").toLowerCase();

        return (
            (!query || searchable.includes(query)) &&
            (!selectedWarehouse || order.warehouse_id === selectedWarehouse) &&
            (!selectedLevel || order.inventory_level === selectedLevel)
        );
    });

    const displayOrders = [...filteredOrders]
        .sort((a, b) =>
            toTimestamp(b.last_updated || b.timestamp) -
            toTimestamp(a.last_updated || a.timestamp)
        )
        .slice(0, 30);

    renderSalesAnalysis(allOrders, realtimeWarehouses);

    allOrders.forEach(o => {
        totalOrders++;
        totalInv += Number(o.inventory || 0);
        const orderStatus = String(o.status || "Pending");
        if (orderStatusCounts[orderStatus] !== undefined) {
            orderStatusCounts[orderStatus]++;
        }

        if (o.reorder_required === true) reorder++;

        let statusClass = "ok";
        const level = String(
    o.inventory_level || ""
);

if (
    level === "LOW" ||
    level === "CRITICAL" ||
    level === "OUT_OF_STOCK"
) {
    if (level === "LOW") lowStock++;
    if (level === "CRITICAL") criticalStock++;
    if (level === "OUT_OF_STOCK") outOfStock++;
}
else if (

    String(o.inventory_level).includes("LOW")
    ||
    o.reorder_required === true

) {

    statusClass = "warning";
    lowStock++;

} else {
    normalStock++;
}
    });

    displayOrders.forEach(o => {
        let statusClass = "ok";
        const level = String(o.inventory_level || "");

        if (
            level === "LOW" ||
            level === "CRITICAL" ||
            level === "OUT_OF_STOCK" ||
            String(o.inventory_level).includes("LOW") ||
            o.reorder_required === true
        ) {
            statusClass = "warning";
        }

        ordersDiv.innerHTML += `
            <div class="card ${statusClass}">
                <strong> ${o.order_id || 'N/A'}</strong><br>
                <span style="color:${getStatusColor(o.status)}">${o.status || '-'}</span><br>
                Kho: ${o.warehouse_id || '-'} | Order Quantity: ${o.order_quantity ?? 0} | Tồn: ${o.inventory ?? 0} | Demand: ${o.future_demand ?? 0}<br>
                Level: <strong>${o.inventory_level || '-'}</strong> - ${o.inventory_level_description || getInventoryLevelDescription(o.inventory_level)}<br>
                ROP: ${o.reorder_point ?? '-'} | Cần nhập: ${o.reorder_quantity ?? 0}
            </div>`;

        tableBody.innerHTML += `
            <tr class="order-row" data-order-id="${escapeAttribute(o.order_id || "")}" tabindex="0">
                <td>${o.order_id || '-'}</td>
                <td>${o.status || '-'}</td>
                <td>${o.warehouse_id || '-'}</td>
                <td>${o.order_quantity ?? 0}</td>
                <td>${o.inventory_before ?? '-'}</td>
                <td>${o.inventory ?? 0}</td>
                <td>${o.future_demand ?? 0}</td>
                <td>
                    <span class="level-badge level-${o.inventory_level || 'NORMAL'}">
                        ${o.inventory_level || '-'}
                    </span>
                    ${o.inventory_level_description || getInventoryLevelDescription(o.inventory_level)}
                </td>
                <td>
                    <span class="replenish-badge replenish-${o.inventory_level || 'NORMAL'}">
                        ${getReplenishmentLabel(o.inventory_level)}
                    </span>
                </td>
                <td>${o.reorder_point ?? '-'}</td>
                <td>${o.reorder_quantity ?? 0}</td>
            </tr>`;
    });
    // Update Stats
    setText("pendingOrders", orderStatusCounts.Pending);
    setText("processingOrders", orderStatusCounts.Processing);
    setText("shippingOrders", orderStatusCounts.Shipping);
    setText("deliveredOrders", orderStatusCounts.Delivered);
    setText("cancelledOrders", orderStatusCounts.Cancelled);
    setText("tabAllCount", totalOrders);
    setText("tabNormalCount", normalStock);
    setText("tabLowCount", lowStock);
    setText("tabCriticalCount", criticalStock);
    setText("tabOutCount", outOfStock);
    setText("inventoryTotalTracked", totalOrders);
    setText("inventoryNormalStock", normalStock);
    setText("inventoryLowStock", lowStock);
    setText("inventoryCriticalStock", criticalStock);
    setText("inventoryOutStock", outOfStock);
    setText("inventoryReorderStock", reorder);
    renderNotifications(allOrders, toTimestamp);
    if (selectedOrderDetailId) {
        renderOrderDetail(selectedOrderDetailId);
    } else if (!orderDetailsView.classList.contains("view-hidden")) {
        renderOrderDetailsList();
    }
}

function getStatusColor(status) {
    const colors = { "Pending":"#f97316", "Processing":"#3b82f6", "Shipping":"#eab308", "Delivered":"#22c55e", "Cancelled":"#ef4444" };
    return colors[status] || "#94a3b8";
}

function getInventoryLevelDescription(level) {
    const descriptions = {
        "NORMAL": "Tồn kho an toàn",
        "LOW": "Tồn kho thấp",
        "CRITICAL": "Tồn kho rất thấp",
        "OUT_OF_STOCK": "Ht hng"
    };
    return descriptions[level] || "Không xác định";
}

function getReplenishmentLabel(level) {
    const labels = {
        "NORMAL": " Bnh thng",
        "LOW": " Bổ sung sớm",
        "CRITICAL": " Bổ sung gấp",
        "OUT_OF_STOCK": " Bổ sung ngay"
    };
    return labels[level] || "N/A";
}




function formatDetailTime(value, fallback = "-") {
    const timestamp = Number(value || 0);
    if (!timestamp) return fallback;
    return new Date(timestamp < 1000000000000 ? timestamp * 1000 : timestamp)
        .toLocaleString("vi-VN");
}

function detailValue(value, fallback = "-") {
    return value === undefined || value === null || value === "" ? fallback : value;
}

function orderTimestamp(order) {
    const value = Number(order?.last_updated || order?.timestamp || 0);
    if (Number.isFinite(value) && value > 0) return value;
    const parsed = Date.parse(order?.last_updated_text || "");
    return Number.isFinite(parsed) ? parsed : 0;
}

function openOrderDetail(orderId) {
    if (!orderId) return;
    selectedOrderDetailId = orderId;
    showMenuView(orderDetailsNav, orderDetailsView);
    setBreadcrumb(["Trang chủ", "Quản lý sản phẩm", "Chi tiết đơn hàng"]);
    renderOrderDetail(orderId);
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function showOrderDetailsList() {
    selectedOrderDetailId = null;
    showMenuView(orderDetailsNav, orderDetailsView);
    setBreadcrumb(["Trang chủ", "Quản lý sản phẩm", "Chi tiết đơn hàng"]);
    renderOrderDetailsList();
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderOrderDetailsList() {
    const container = document.getElementById("orders");
    if (!container) return;

    const orders = Object.values(latestFirebaseOrders || {})
        .sort((a, b) => orderTimestamp(b) - orderTimestamp(a));

    if (!orders.length) {
        container.innerHTML = `
            <div class="order-detail-empty">
                Ch\u01b0a c\u00f3 \u0111\u01a1n h\u00e0ng \u0111\u1ec3 hi\u1ec3n th\u1ecb. H\u00e3y t\u1ea1o \u0111\u01a1n h\u00e0ng tr\u01b0\u1edbc.
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <div class="order-detail-list">
            ${orders.map(order => {
                const level = order.inventory_level || "NORMAL";
                return `
                    <button class="order-detail-list-item" type="button" data-order-id="${escapeAttribute(order.order_id || "")}">
                        <div class="order-list-main">
                            <strong>${escapeAttribute(order.order_id || "-")}</strong>
                            <span>${escapeAttribute(order.warehouse_id || "-")} / ${escapeAttribute(order.product_id || "-")}</span>
                        </div>
                        <div class="order-list-meta">
                            <span class="status-pill" style="color:${getStatusColor(order.status)}">${escapeAttribute(order.status || "-")}</span>
                            <span class="level-badge level-${escapeAttribute(level)}">${escapeAttribute(level)}</span>
                            <span>T\u1ed3n sau: ${escapeAttribute(detailValue(order.inventory))}</span>
                            <span>D\u1ef1 b\u00e1o: ${escapeAttribute(detailValue(order.future_demand))}</span>
                            <span>C\u1ea7n nh\u1eadp: ${escapeAttribute(detailValue(order.reorder_quantity, 0))}</span>
                        </div>
                    </button>
                `;
            }).join("")}
        </div>
    `;
}

function renderOrderDetail(orderId) {
    const container = document.getElementById("orders");
    if (!container) return;

    if (!orderId) {
        renderOrderDetailsList();
        return;
    }

    const order = latestFirebaseOrders?.[orderId] ||
        Object.values(latestFirebaseOrders || {}).find(item =>
            String(item.order_id || "") === String(orderId)
        );

    if (!order) {
        container.innerHTML = `
            <div class="order-detail-empty">
                Kh\u00f4ng t\u00ecm th\u1ea5y d\u1eef li\u1ec7u chi ti\u1ebft cho \u0111\u01a1n ${escapeAttribute(orderId)}.
                <div style="margin-top:12px"><button class="secondary-action-btn" data-action="back-order-list" type="button">Quay l\u1ea1i danh s\u00e1ch</button></div>
            </div>
        `;
        return;
    }

    const demand7 = detailValue(order.future_demand);
    const demand30 = order.future_demand_30 != null
        ? order.future_demand_30
        : forecast30From7(order.future_demand || 0);
    const logs = Array.isArray(order.processing_logs)
        ? order.processing_logs
        : [];
    const level = order.inventory_level || "NORMAL";

    const detailRows = [
        ["M\u00e3 \u0111\u01a1n h\u00e0ng", order.order_id],
        ["Tr\u1ea1ng th\u00e1i", order.status],
        ["Kho", order.warehouse_id],
        ["S\u1ea3n ph\u1ea9m", order.product_id],
        ["Order Quantity", order.order_quantity],
        ["T\u1ed3n tr\u01b0\u1edbc", order.inventory_before],
        ["T\u1ed3n sau", order.inventory],
        ["D\u1ef1 b\u00e1o 7 ng\u00e0y", demand7],
        ["D\u1ef1 b\u00e1o 30 ng\u00e0y", demand30],
        ["S\u1ea3n ph\u1ea9m / Ng\u00e0y", order.daily_sales],
        ["S\u1ed1 b\u00e1n 7 ng\u00e0y qua", sales7Days(order)],
        ["S\u1ed1 b\u00e1n 30 ng\u00e0y qua", sales30Days(order)],
        ["Reorder Point", order.reorder_point],
        ["C\u1ea7n nh\u1eadp", order.reorder_quantity],
        ["M\u1ee9c t\u1ed3n kho", `${level} - ${order.inventory_level_description || getInventoryLevelDescription(level)}`],
        ["M\u1ee9c \u0111\u1ed9 b\u1ed5 sung", getReplenishmentLabel(level)],
        ["C\u1ea3nh b\u00e1o", order.alert],
        ["Model", order.model_mode],
        ["Phi\u00ean b\u1ea3n model", order.model_version],
        ["Prediction latency", order.prediction_latency_ms != null ? `${order.prediction_latency_ms} ms` : "-"],
        ["Backend latency", order.processing_latency_ms != null ? `${order.processing_latency_ms} ms` : "-"],
        ["C\u1eadp nh\u1eadt l\u00fac", order.last_updated_text || formatDetailTime(order.last_updated || order.timestamp)]
    ];

    container.innerHTML = `
        <div class="order-detail-layout">
            <div class="order-detail-main">
                <button class="secondary-action-btn order-detail-back" data-action="back-order-list" type="button">\u2190 Danh s\u00e1ch \u0111\u01a1n h\u00e0ng</button>
                <div class="order-detail-header">
                    <div>
                        <span class="detail-eyebrow">\u0110\u01a1n h\u00e0ng</span>
                        <h2>${escapeAttribute(order.order_id || "-")}</h2>
                        <p>${escapeAttribute(order.warehouse_id || "-")} / ${escapeAttribute(order.product_id || "-")}</p>
                    </div>
                    <div class="detail-status-group">
                        <span class="status-pill" style="color:${getStatusColor(order.status)}">${escapeAttribute(order.status || "-")}</span>
                        <span class="level-badge level-${escapeAttribute(level)}">${escapeAttribute(level)}</span>
                    </div>
                </div>
                <div class="order-detail-grid">
                    ${detailRows.map(([label, value]) => `
                        <div class="order-detail-item">
                            <span>${escapeAttribute(label)}</span>
                            <strong>${escapeAttribute(detailValue(value))}</strong>
                        </div>
                    `).join("")}
                </div>
            </div>
            <div class="order-detail-log">
                <h4>Nh\u1eadt k\u00fd x\u1eed l\u00fd</h4>
                ${logs.length ? logs.map(item => `
                    <div class="detail-log-line">
                        <span>${escapeAttribute(item.time || "--:--:--")}</span>
                        <strong>${escapeAttribute(item.message || "")}</strong>
                    </div>
                `).join("") : '<div class="detail-log-line"><strong>Ch\u01b0a c\u00f3 nh\u1eadt k\u00fd x\u1eed l\u00fd.</strong></div>'}
            </div>
        </div>
    `;
}

function showOrderResult(order) {
    document.getElementById("resultBefore").textContent =
        order.inventory_before ?? "-";
    document.getElementById("resultQuantity").textContent =
        order.order_quantity ?? "-";
    const demand7 = toNumber(order.future_demand, 0);
    const demand30 = order.future_demand_30 != null
        ? toNumber(order.future_demand_30, 0)
        : forecast30From7(demand7);
    document.getElementById("resultDemand7").textContent =
        demand7;
    document.getElementById("resultDemand30").textContent =
        demand30;
    document.getElementById("resultAfter").textContent =
        order.inventory ?? "-";
    document.getElementById("resultRop").textContent =
        order.reorder_point ?? "-";
    document.getElementById("resultReorder").textContent =
        order.reorder_quantity ?? "-";
    document.getElementById("resultLevel").textContent =
        order.inventory_level ?? "-";
    document.getElementById("resultAlert").textContent =
        order.alert ?? "-";
}

function showFormLogs(logs) {
    const container = document.getElementById("realtimeLog");
    if (!container) return;
    container.innerHTML = "";
    (logs || []).slice(-10).forEach(item => {
        const line = document.createElement("div");
        line.className = "log-line";
        line.textContent = `${item.time || "--:--:--"} - ${item.message || ""}`;
        container.appendChild(line);
    });
}

document.getElementById("formOrderDate").value =
    new Date().toISOString().slice(0, 10);

document.getElementById("newOrderForm").addEventListener("submit", async event => {
    event.preventDefault();
    const button = document.getElementById("submitOrderBtn");
    const message = document.getElementById("formMessage");
    button.disabled = true;
    message.className = "form-message";
    message.textContent = "Đang chạy dự báo và xử lý tồn kho...";

    const payload = {
        order_id: document.getElementById("formOrderId").value.trim(),
        product_id: document.getElementById("formProductId").value.trim(),
        warehouse_id: document.getElementById("formWarehouseId").value.trim(),
        order_quantity: document.getElementById("formOrderQuantity").value,
        lead_time: document.getElementById("formLeadTime").value,
        order_date: document.getElementById("formOrderDate").value,
        daily_sales: document.getElementById("formDailySales").value
    };

    try {
        const response = await fetch("/api/orders/process", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (!response.ok || !result.ok) {
            const details = result.errors
                ? Object.values(result.errors).join(" ")
                : result.error || "Khng th x l n hng.";
            throw new Error(details);
        }
        showFormLogs(result.logs);
        message.className = result.order.fallback_used
            ? "form-message error"
            : "form-message success";
        message.textContent = result.order.fallback_used
            ? ` x l ${result.order.order_id} bng FALLBACK: ${result.order.prediction_error || "model khng kh dng"}.`
            : ` x l ${result.order.order_id} bng ${result.order.model_mode} (${result.order.model_version}); Dashboard nhn qua onValue.`;
    } catch (error) {
        message.className = "form-message error";
        message.textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

document.getElementById("addProductForm").addEventListener("submit", async event => {
    event.preventDefault();
    const button = document.getElementById("addProductBtn");
    const message = document.getElementById("addProductMessage");
    button.disabled = true;
    message.className = "form-message";
    message.textContent = "Đang thêm sản phẩm vào Firebase...";

    try {
        const response = await fetch("/api/products", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                warehouse_id:
                    document.getElementById("newProductWarehouse").value.trim(),
                product_id:
                    document.getElementById("newProductId").value.trim(),
                stock:
                    document.getElementById("newProductStock").value
            })
        });
        const result = await response.json();
        if (!response.ok || !result.ok) {
            const details = result.errors
                ? Object.values(result.errors).join(" ")
                : result.error || "Không thể thêm sản phẩm.";
            throw new Error(details);
        }
        message.className = "form-message success";
        message.textContent =
            `Đã thêm ${result.product.product_id} vào ${result.product.warehouse_id}; onValue đã đồng bộ.`;
    } catch (error) {
        message.className = "form-message error";
        message.textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

document.getElementById("restockForm").addEventListener("submit", async event => {
    event.preventDefault();
    const button = document.getElementById("restockBtn");
    const message = document.getElementById("restockMessage");
    button.disabled = true;
    message.className = "form-message";
    message.textContent = "Đang bổ sung hàng vào kho...";

    try {
        const response = await fetch("/api/inventory/restock", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                warehouse_id:
                    document.getElementById("restockWarehouse").value.trim(),
                product_id:
                    document.getElementById("restockProductId").value.trim(),
                restock_quantity:
                    document.getElementById("restockQuantity").value
            })
        });
        const result = await response.json();
        if (!response.ok || !result.ok) {
            const details = result.errors
                ? Object.values(result.errors).join(" ")
                : result.error || "Không thể nhập thêm hàng.";
            throw new Error(details);
        }
        const item = result.restock;
        document.getElementById("restockBefore").textContent =
            item.stock_before;
        document.getElementById("restockAdded").textContent =
            item.restock_quantity;
        document.getElementById("restockAfter").textContent =
            item.stock_after;
        document.getElementById("restockLevel").textContent =
            `${item.inventory_level} - ${item.inventory_level_description}`;
        document.getElementById("restockRop").textContent =
            item.reorder_point;
        document.getElementById("restockNeed").textContent =
            item.reorder_quantity;
        message.className = "form-message success";
        message.textContent =
            `Đã nhập thêm ${item.restock_quantity} cho ${item.product_id} tại ${item.warehouse_id}; Dashboard nhận qua onValue.`;
    } catch (error) {
        message.className = "form-message error";
        message.textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

fetch("/api/model-info")
    .then(response => response.json())
    .then(info => {
        document.getElementById("metricMae").textContent =
            Number(info.mae).toFixed(2);
        document.getElementById("metricRmse").textContent =
            Number(info.rmse).toFixed(2);
        document.getElementById("metricR2").textContent =
            Number(info.r2).toFixed(4);
        document.getElementById("modelLoadStatus").textContent = info.loaded
            ? `${info.name} + ${info.encoding}  t?i thnh cng`
            : "Model cha t?i c - ang dng fallback";
        document.getElementById("modelLoadStatus").className = info.loaded
            ? "firebase-connected"
            : "firebase-error";
    })
    .catch(() => {
        document.getElementById("modelLoadStatus").textContent =
            "Khng c c trng thi model";
    });

function resetInventoryFilters() {
    document.getElementById("searchInput").value = "";
    document.getElementById("warehouseFilter").value = "";
    document.getElementById("levelFilter").value = "";
    document.querySelectorAll(".inventory-tab").forEach(button =>
        button.classList.toggle("active", button.dataset.level === "")
    );
    scheduleRender();
}
