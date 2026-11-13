import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const filename = fileURLToPath(import.meta.url);

const exportsObject = {};
const { outputText } = ts.transpileModule(readFileSync(new URL("chart-utils.ts", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
});
runInNewContext(outputText, { exports: exportsObject });
const { aggregateDailyCandles, extractLineSeriesData } = exportsObject;
const data = ["2026-10-30", "2026-11-02", "2026-11-03", "2026-11-09"].map((day, i) => ({
  time: `${day} 15:30:00`, open: 100 + i, high: 110 + i, low: 90 + i,
  close: 105 + i, volume: i + 1, ma5: i === 2 ? 102 : null,
}));
const plain = value => JSON.parse(JSON.stringify(value));
const stamp = day => Date.parse(`${day}T15:30:00Z`) / 1000;

if (process.argv.includes("--fixture")) {
  process.stdout.write(JSON.stringify(["1W", "1M"].map(tf => ({
    candles: aggregateDailyCandles(data, tf), line: extractLineSeriesData(data, "ma5", tf),
  }))));
} else {
  test("weekly candle and warmed MA share the first trading timestamp", () => {
    const candles = plain(aggregateDailyCandles(data, "1W"));
    assert.deepEqual(candles, [
      { time: stamp("2026-10-30"), open: 100, high: 110, low: 90, close: 105, volume: 1 },
      { time: stamp("2026-11-02"), open: 101, high: 112, low: 91, close: 107, volume: 5 },
      { time: stamp("2026-11-09"), open: 103, high: 113, low: 93, close: 108, volume: 4 },
    ]);
    assert.deepEqual(plain(extractLineSeriesData(data, "ma5", "1W")), [
      { time: stamp("2026-11-02"), value: 102 },
    ]);
  });
  test("monthly MA warmup uses its candle timestamp and all-null groups stay absent", () => {
    assert.deepEqual(plain(extractLineSeriesData(data, "ma5", "1M")), [
      { time: stamp("2026-11-02"), value: 102 },
    ]);
  });
  test("Korean daily grouping is identical across browser timezones", () => {
    const results = ["Asia/Seoul", "America/Los_Angeles", "UTC", "Pacific/Kiritimati"].map(TZ => {
      const child = spawnSync(process.execPath, [filename, "--fixture"], {
        env: { ...process.env, TZ }, encoding: "utf8", timeout: 10000,
      });
      assert.equal(child.status, 0, child.stderr);
      return JSON.parse(child.stdout);
    });
    for (const result of results) assert.deepEqual(result, results[0]);
    assert.deepEqual(results[0][0].candles.map(c => c.volume), [1, 5, 4]);
  });
}
