# coach of HPE Model pipeline
입력 영상으로부터 HPE 데이터셋과 트래킹된 영상을 출력하는 파이프라인을 설계하고자 한다.

> main.sh 실행
``` zsh
./scripts/main.sh test7 --agent false --extract --device cpu
```

> 영상 형식 변경
``` bash
ffmpeg -y -i IMG_1012.mov \
  -map 0:v:0 \
  -map 0:a:0? \
  -c:v libx264 \
  -crf 20 \
  -preset medium \
  -pix_fmt yuv420p \
  -c:a aac \
  -b:a 192k \
  -movflags +faststart \
  output_h264.mp4
```