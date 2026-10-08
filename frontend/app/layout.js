import "./globals.css";
import Sidebar from "../components/Sidebar";

export const metadata = {
  title: "AI-ARCTEG Dashboard",
  description: "Hybrid PV + TEG monitoring with digital twin and ML",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <Sidebar />
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
