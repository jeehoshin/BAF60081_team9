// vite build --mode html 결과(dist-html/)를 파일 하나짜리 HTML로 합친다.
//   dist-html/gachi-galae-prototype.html : 더블클릭해서 여는 파일 (단톡 첨부용)
//   dist-html/artifact.html              : Claude Artifact로 올릴 때 쓰는 본문 (doctype·head 없이)
// 서버에 연결할 수 없는 곳에서 열면 앱이 알아서 저장본(src/data/snapshot.json)으로 보여 준다.
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const dir = "dist-html";
const assets = readdirSync(join(dir, "assets"));
const js = assets.find((f) => f.endsWith(".js"));
const css = assets.find((f) => f.endsWith(".css"));
if (!js || !css) throw new Error("dist-html/assets 에 js·css가 없어요. 먼저 vite build --mode html 을 실행하세요.");

const code = readFileSync(join(dir, "assets", js), "utf8").replace(/<\/script/gi, "<\\/script");
const style = readFileSync(join(dir, "assets", css), "utf8");
const icon = `data:image/svg+xml;base64,${readFileSync("public/mascot.svg").toString("base64")}`;
const fonts = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Jua&display=swap">';

const body = `<div id="root"></div>\n<script type="module">\n${code}\n</script>`;

writeFileSync(
  join(dir, "gachi-galae-prototype.html"),
  `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>같이 갈래? AI 프로토타입</title>
<link rel="icon" href="${icon}">
${fonts}
<style>${style}</style>
</head>
<body>
${body}
</body>
</html>
`,
);

writeFileSync(join(dir, "artifact.html"), `<title>같이 갈래? AI 프로토타입</title>\n${fonts}\n<style>${style}</style>\n${body}\n`);

console.log(`만들었어요: ${dir}/gachi-galae-prototype.html, ${dir}/artifact.html`);
