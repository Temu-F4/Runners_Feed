import type { Metadata } from "next";
import "../styles.css";

export const metadata: Metadata = {
  title: "Runners Feed · Running Form Analysis",
  description: "러닝 영상을 업로드하고 자세 분석 결과를 확인합니다.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
