import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createTheme, MantineProvider } from "@mantine/core";
import "@mantine/core/styles.css";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import "./styles.css";

const theme = createTheme({
  primaryColor: "orange",
  autoContrast: true,
  primaryShade: { light: 6, dark: 4 },
  defaultRadius: "sm",
  fontFamily:
    '"Segoe UI Variable Text", "Segoe UI", ui-sans-serif, system-ui, sans-serif',
  headings: {
    fontFamily:
      '"Segoe UI Variable Display", "Segoe UI", ui-sans-serif, system-ui, sans-serif',
  },
  colors: {
    dark: [
      "#eeeeee",
      "#cccccc",
      "#aaaaaa",
      "#858585",
      "#343434",
      "#292929",
      "#202020",
      "#191919",
      "#111111",
      "#0b0b0b",
    ],
    orange: [
      "#fff1e5",
      "#ffe0c2",
      "#ffc18a",
      "#ffa352",
      "#ff7900",
      "#e66d00",
      "#c75e00",
      "#a64e00",
      "#853e00",
      "#663000",
    ],
    fabric: [
      "#e7f8f5",
      "#cceee8",
      "#9edfd5",
      "#70cec0",
      "#4bbbad",
      "#36a598",
      "#2c887e",
      "#286d66",
      "#255853",
      "#214a46",
    ],
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MantineProvider forceColorScheme="dark" theme={theme}>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </MantineProvider>
  </StrictMode>,
);
