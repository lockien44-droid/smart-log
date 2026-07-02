import { initializeApp } from "firebase/app";
import { getDatabase, ref, onValue } from "firebase/database";

// =========================
// CONFIG
// =========================
const firebaseConfig = {
  apiKey: "YOUR_API_KEY",
  authDomain: "smart-logistics-system-75a42.firebaseapp.com",
  databaseURL:
    "https://smart-logistics-system-75a42-default-rtdb.asia-southeast1.firebasedatabase.app",
  projectId: "smart-logistics-system-75a42",
  storageBucket:
    "smart-logistics-system-75a42.appspot.com",
  messagingSenderId: "YOUR_MESSAGING_SENDER_ID",
  appId: "YOUR_APP_ID"
};

// =========================
// INIT APP
// =========================
const app = initializeApp(firebaseConfig);

// =========================
// REALTIME DB
// =========================
const db = getDatabase(app);

// =========================
// EXPORT (MODERN STYLE)
// =========================
export {
  db,
  ref,
  onValue
};