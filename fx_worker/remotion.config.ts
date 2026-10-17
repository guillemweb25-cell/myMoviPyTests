// Config solo para `remotion studio` (desarrollo). El render del servidor pasa
// sus propias opciones a renderMedia(), así que lo de aquí no le afecta.
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.overrideWebpackConfig((config) => config);
