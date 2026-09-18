import { TooltipProvider } from "@/components/ui";
import { RouterProvider } from "react-router-dom";

import { router } from "./router";

export function App() {
  return (
    <TooltipProvider>
      <RouterProvider router={router} />
    </TooltipProvider>
  );
}
