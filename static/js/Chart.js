const db = firebase.database();

// =========================
// STATUS CHART (BAR)
// =========================
const statusChart = new Chart(
    document.getElementById("statusChart"),
    {
        type: "bar",
        data: {
            labels: ["Delivered", "Cancelled"],
            datasets: [{
                label: "Orders",
                data: [0, 0],
                backgroundColor: ["#22c55e", "#ef4444"]
            }]
        },
        options: {
            responsive: true,
            animation: false
        }
    }
);

// =========================
// INVENTORY CHART (LINE)
// =========================
const inventoryChart = new Chart(
    document.getElementById("inventoryChart"),
    {
        type: "line",
        data: {
            labels: [],
            datasets: [
                {
                    label: "Inventory",
                    data: [],
                    borderColor: "#38bdf8",
                    tension: 0.3
                },
                {
                    label: "Demand",
                    data: [],
                    borderColor: "#f97316",
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            animation: false
        }
    }
);

// =========================
// REALTIME UPDATE FROM FIREBASE
// =========================
firebase.database().ref("orders").on("value", (snapshot) => {

    const data = snapshot.val();

    if (!data) return;

    const orders = Object.values(data);

    // =========================
    // STATUS CALC
    // =========================
    let delivered = 0;
    let cancelled = 0;

    orders.forEach(o => {

        const status = (o.status || "").toLowerCase();

        if (status === "delivered") delivered++;
        if (status === "cancelled") cancelled++;

    });

    statusChart.data.datasets[0].data = [
        delivered,
        cancelled
    ];

    statusChart.update();

    // =========================
    // INVENTORY CHART
    // =========================
    const labels = [];
    const inventoryData = [];
    const demandData = [];

    orders.forEach(o => {

        labels.push(o.order_id || "N/A");

        inventoryData.push(
            Number(o.inventory || 0)
        );

        demandData.push(
            Number(o.future_demand || 0)
        );
    });

    inventoryChart.data.labels = labels;
    inventoryChart.data.datasets[0].data = inventoryData;
    inventoryChart.data.datasets[1].data = demandData;

    inventoryChart.update();

});