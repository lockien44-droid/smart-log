import React, { useEffect, useState, useMemo } from "react";
import { db, ref, onValue } from "./firebase";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar
} from "recharts";

function App() {

  const [orders, setOrders] = useState([]);

  // =========================
  // FIREBASE REALTIME
  // =========================
  useEffect(() => {

    const ordersRef = ref(db, "orders");

    const unsubscribe = onValue(ordersRef, (snapshot) => {

      const data = snapshot.val();

      if (!data) {
        setOrders([]);
        return;
      }

      // SAFE CONVERT + CLEAN DATA
      const clean = Object.values(data).map(o => ({
        order_id: o.order_id ?? "N/A",
        status: o.status ?? "Unknown",
        inventory: Number(o.inventory ?? 0),
        future_demand: Number(o.future_demand ?? 0)
      }));

      setOrders(clean);
    });

    return () => unsubscribe();

  }, []);

  // =========================
  // KPI (OPTIMIZED)
  // =========================
  const kpi = useMemo(() => {

    const totalOrders = orders.length;

    const totalInventory = orders.reduce(
      (sum, o) => sum + o.inventory,
      0
    );

    const totalDemand = orders.reduce(
      (sum, o) => sum + o.future_demand,
      0
    );

    const lowStock = orders.filter(
      o => o.inventory < o.future_demand
    ).length;

    return {
      totalOrders,
      totalInventory,
      totalDemand,
      lowStock
    };

  }, [orders]);

  // =========================
  // CHART DATA (SAFE + STABLE)
  // =========================
  const chartData = useMemo(() => {

    return orders.map(o => ({
      name: o.order_id,
      inventory: o.inventory,
      demand: o.future_demand
    }));

  }, [orders]);

  return (
    <div style={styles.container}>

      <h1 style={{ color: "#38bdf8" }}>
        🚚 Smart Logistics AI Dashboard
      </h1>

      {/* KPI */}
      <div style={styles.kpiGrid}>

        <div style={cardStyle}>
          <h3>Total Orders</h3>
          <h2>{kpi.totalOrders}</h2>
        </div>

        <div style={cardStyle}>
          <h3>Total Inventory</h3>
          <h2>{kpi.totalInventory}</h2>
        </div>

        <div style={cardStyle}>
          <h3>Forecast Demand</h3>
          <h2>{kpi.totalDemand}</h2>
        </div>

        <div style={cardStyle}>
          <h3>Low Stock Alerts</h3>
          <h2 style={{ color: "#ef4444" }}>
            {kpi.lowStock}
          </h2>
        </div>

      </div>

      {/* LINE CHART */}
      <div style={chartContainer}>

        <h2>📈 Inventory vs Demand Trend</h2>

        <ResponsiveContainer width="100%" height={350}>

          <LineChart data={chartData}>

            <CartesianGrid strokeDasharray="3 3" />

            <XAxis dataKey="name" />

            <YAxis />

            <Tooltip />

            <Legend />

            <Line
              type="monotone"
              dataKey="inventory"
              stroke="#38bdf8"
              strokeWidth={3}
            />

            <Line
              type="monotone"
              dataKey="demand"
              stroke="#f97316"
              strokeWidth={3}
            />

          </LineChart>

        </ResponsiveContainer>

      </div>

      {/* BAR CHART */}
      <div style={chartContainer}>

        <h2>📊 Inventory vs Demand Comparison</h2>

        <ResponsiveContainer width="100%" height={350}>

          <BarChart data={chartData}>

            <CartesianGrid strokeDasharray="3 3" />

            <XAxis dataKey="name" />

            <YAxis />

            <Tooltip />

            <Legend />

            <Bar dataKey="inventory" fill="#22c55e" />
            <Bar dataKey="demand" fill="#ef4444" />

          </BarChart>

        </ResponsiveContainer>

      </div>

      {/* TABLE */}
      <div style={{ marginTop: 30 }}>

        <h2>📦 Realtime Order Tracking</h2>

        <table style={styles.table}>

          <thead>
            <tr>
              <th style={th}>Order ID</th>
              <th style={th}>Status</th>
              <th style={th}>Inventory</th>
              <th style={th}>Future Demand</th>
            </tr>
          </thead>

          <tbody>

            {orders.map((order) => (

              <tr key={order.order_id}>

                <td style={td}>{order.order_id}</td>
                <td style={td}>{order.status}</td>
                <td style={td}>{order.inventory}</td>
                <td style={td}>{order.future_demand}</td>

              </tr>

            ))}

          </tbody>

        </table>

      </div>

    </div>
  );
}

// =========================
// STYLES
// =========================
const styles = {
  container: {
    background: "#0f172a",
    minHeight: "100vh",
    color: "white",
    padding: "20px"
  },

  kpiGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4,1fr)",
    gap: "15px",
    marginBottom: "30px"
  },

  table: {
    width: "100%",
    borderCollapse: "collapse",
    background: "#1e293b"
  }
};

const cardStyle = {
  background: "#1e293b",
  padding: "20px",
  borderRadius: "10px",
  textAlign: "center"
};

const chartContainer = {
  background: "#1e293b",
  padding: "20px",
  borderRadius: "10px",
  marginBottom: "30px"
};

const th = {
  border: "1px solid #334155",
  padding: "10px",
  background: "#0f172a"
};

const td = {
  border: "1px solid #334155",
  padding: "10px",
  textAlign: "center"
};

export default App;