import { stopE2EWorker } from "./global-setup";

export default function globalTeardown() {
  stopE2EWorker();
}
