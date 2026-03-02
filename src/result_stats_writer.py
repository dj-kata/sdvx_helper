from PIL import Image, ImageDraw, ImageFont
import os
from src.classes import *
from src.funcs import *

# 難易度ごとの色マッピング: (fill, glow_color)
_DIFFICULTY_COLORS = {
    difficulty.another:     ((250, 100, 100), (150, 0, 0)),
    difficulty.leggendaria: ((250, 100, 250), (80, 0, 80)),
    difficulty.hyper:       ((250, 250, 100), (80, 80, 0)),
    difficulty.normal:      ((100, 100, 250), (0, 0, 80)),
    difficulty.beginner:    ((100, 250, 100), (0, 80, 0)),
}

# クリアランプごとの表示: (display_text, fill, glow_color)
_LAMP_DISPLAY = {
    clear_lamp.assist: ('A-CLEAR',   (255, 155, 250), (80, 0, 80)),
    clear_lamp.easy:   ('E-CLEAR',   (100, 255, 100), (80, 150, 80)),
    clear_lamp.clear:  (None,        (100, 190, 255), (80, 100, 150)),  # None = lamp.name.upper()を使用
    clear_lamp.hard:   ('H-CLEAR',   (255, 50, 100),  (150, 30, 50)),
    clear_lamp.exh:    ('EXH-CLEAR', (255, 255, 100), (150, 150, 50)),
    clear_lamp.fc:     ('F-COMBO',   (255, 170, 250), (200, 50, 150)),
}

class ResultStatsWriter:
    """リザルト画像に統計情報を埋め込むためのクラス"""
    
    def __init__(self, font_dir="fonts"):
        """
        Args:
            font_dir: フォントファイルを保存するディレクトリ（未使用）
        """
        # フォント読み込み
        self.title_font = self._load_font(size=55, bold=True)
        self.main_font = self._load_font(size=44)
        self.sub_font = self._load_font(size=36)
    
    def _load_font(self, size=28, bold=False):
        """システムフォントを読み込む"""
        # Windowsフォント
        windows_fonts = [
            "C:/Windows/Fonts/meiryob.ttc" if bold else "C:/Windows/Fonts/meiryo.ttc",  # メイリオ
            "C:/Windows/Fonts/YuGothB.ttc" if bold else "C:/Windows/Fonts/YuGothM.ttc",  # 游ゴシック
            "C:/Windows/Fonts/msgothic.ttc",  # MSゴシック
        ]
        
        for font_path in windows_fonts:
            if os.path.exists(font_path):
                try:
                    return ImageFont.truetype(font_path, size)
                except:
                    pass
        
        return ImageFont.load_default()
    
    def write_statistics(
        self,
        img,
        title,
        level,
        play_style:play_style,
        difficulty:difficulty,
        ex_score,
        bp,
        max_notes,
        lamp:clear_lamp,
        bpi=None,
        sp12_clear:clear_lamp=None,
        sp12_hard:clear_lamp=None,
        position=(600, 405),  # (x, y) 座標で指定
        box_width=790,     # ボックス幅（Noneで画像幅）
        box_height=400,
        box_alpha=230       # 背景の透明度 (0-255)
    ):
        """
        リザルト画像に統計情報を書き込む。
        
        Args:
            position: 描画位置 (x, y) のタプル。"top"/"bottom"も可
            box_width: ボックス幅（Noneで画像幅いっぱい）
            box_alpha: 背景の透明度 (0=完全透明, 255=不透明)
        """
        # 画像を開く
        max_score = max_notes * 2
        
        # RGBA変換（透明度サポート）
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # 半透明レイヤーを作成
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # 位置を解決（文字列または座標）
        if position == "top":
            x, y = 40, 10
        elif position == "bottom":
            x, y = 40, img.height - 220
        else:
            x, y = position
        
        # ボックス幅のデフォルト値
        if box_width is None:
            box_width = img.width - x * 2
        
        line_height = self.main_font.size + 15
        
        # 背景ボックスを描画（半透明、透明度を指定可能）
        self._draw_rounded_rectangle(
            draw, 
            (x - 40, y - 10, x - 40 + box_width, y + box_height),
            radius=5,
            fill=(0, 0, 0, box_alpha)  # 透明度を引数で指定
        )
        
        # 1行目: 曲名と難易度（難易度部分は必ず表示）
        y+=20
        difficulty_part = f" ({play_style}{difficulty})"
        text = self._truncate_title_with_difficulty(draw, title, '', self.title_font, box_width - 30)
        self._draw_text_with_glow(draw, (x, y), text, self.title_font, 
                                   fill=(255, 255, 255), glow_color=(70, 70, 70))
        y += self.title_font.size+40
        
        # Lv, その他難易度
        text = f"{get_chart_name(play_style,difficulty)} "
        text = self._truncate_text(draw, text, self.sub_font, box_width - 30)
        diff_fill, diff_glow = _DIFFICULTY_COLORS.get(difficulty, ((255, 255, 255), (50, 50, 50)))
        self._draw_text_with_glow(draw, (x, y), text, self.sub_font,
                                   fill=diff_fill, glow_color=diff_glow)
        text = f"Lv{level} "
        text = self._truncate_text(draw, text, self.main_font, box_width - 30)
        self._draw_text_with_glow(draw, (x+100, y), text, self.sub_font,
                                   fill=(100, 255, 250), glow_color=(0, 150, 150))
        if sp12_clear and sp12_hard:
            text = f" ({sp12_clear}/{sp12_hard})"
            text = self._truncate_text(draw, text, self.sub_font, box_width - 30)
            self._draw_text_with_glow(draw, (x+200, y), text, self.sub_font,
                                       fill=(250, 255, 255), glow_color=(50, 50, 50))
        y += self.sub_font.size + 30

        # クリアランプ
        if lamp in _LAMP_DISPLAY:
            lamp_text, lamp_fill, lamp_glow = _LAMP_DISPLAY[lamp]
            if lamp_text is None:
                lamp_text = lamp.name.upper()
            lamp_text = self._truncate_text(draw, lamp_text, self.main_font, box_width - 30)
            self._draw_text_with_glow(draw, (x, y), lamp_text, self.main_font,
                                       fill=lamp_fill, glow_color=lamp_glow)
        y += line_height

        # スコア,BP
        text = f"ex: {ex_score}/{max_score}, bp: {bp}/{max_notes}"
        text = self._truncate_text(draw, text, self.main_font, box_width - 30)
        self._draw_text_with_glow(draw, (x, y), text, self.main_font,
                                   fill=(100, 255, 100), glow_color=(0, 80, 0))
        y += line_height
        
        # 4行目: レート、BPI、レベル（明るい黄色）
        rate = ex_score / max_score*100
        parts = [f"rate: {rate:.2f}%"]
        if bpi is not None:
            parts.append(f"BPI: {bpi:.2f}")
        
        text = ", ".join(parts)
        text = self._truncate_text(draw, text, self.main_font, box_width - 30)
        self._draw_text_with_glow(draw, (x, y), text, self.main_font,
                                   fill=(255, 255, 100), glow_color=(80, 80, 0))
        
        # オーバーレイを合成
        img = Image.alpha_composite(img, overlay)
        
        # RGB変換して保存
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        return img

    def _truncate_title_with_difficulty(self, draw, title, difficulty_part, font, max_width):
        """
        曲名を省略するが、難易度部分は必ず表示する
        
        Args:
            draw: ImageDrawオブジェクト
            title: 曲名（難易度なし）
            difficulty_part: 難易度部分（例: " (SPA)"）
            font: フォント
            max_width: 最大幅
        
        Returns:
            str: 省略された曲名 + 難易度
        """
        # 難易度部分の幅を計算
        difficulty_bbox = draw.textbbox((0, 0), difficulty_part, font=font)
        difficulty_width = difficulty_bbox[2] - difficulty_bbox[0]
        
        # 曲名に使える幅
        available_width = max_width - difficulty_width
        
        # 曲名全体が収まるかチェック
        title_bbox = draw.textbbox((0, 0), title, font=font)
        title_width = title_bbox[2] - title_bbox[0]
        
        if title_width <= available_width:
            # 収まる場合はそのまま
            return title + difficulty_part
        
        # 収まらない場合、曲名を省略
        ellipsis = "..."
        ellipsis_bbox = draw.textbbox((0, 0), ellipsis, font=font)
        ellipsis_width = ellipsis_bbox[2] - ellipsis_bbox[0]
        
        # 曲名 + "..." の幅が収まるように調整
        available_for_title = available_width - ellipsis_width
        
        for i in range(len(title), 0, -1):
            truncated_title = title[:i]
            bbox = draw.textbbox((0, 0), truncated_title, font=font)
            truncated_width = bbox[2] - bbox[0]
            
            if truncated_width <= available_for_title:
                return truncated_title + ellipsis + difficulty_part
        
        return ellipsis + difficulty_part
    
    def _truncate_text(self, draw, text, font, max_width):
        """
        テキストが長すぎる場合、省略記号を付けて切り詰める
        
        Args:
            draw: ImageDrawオブジェクト
            text: 元のテキスト
            font: フォント
            max_width: 最大幅
        
        Returns:
            str: 切り詰められたテキスト
        """
        # テキストの幅を取得
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        
        if text_width <= max_width:
            return text
        
        # 省略記号を追加して切り詰め
        ellipsis = "..."
        ellipsis_bbox = draw.textbbox((0, 0), ellipsis, font=font)
        ellipsis_width = ellipsis_bbox[2] - ellipsis_bbox[0]
        
        # 1文字ずつ削りながら幅をチェック
        for i in range(len(text), 0, -1):
            truncated = text[:i] + ellipsis
            bbox = draw.textbbox((0, 0), truncated, font=font)
            truncated_width = bbox[2] - bbox[0]
            
            if truncated_width <= max_width:
                return truncated
        
        return ellipsis
    
    def _draw_rounded_rectangle(self, draw, coords, radius=10, fill=(0, 0, 0, 180)):
        """角丸矩形を描画"""
        x1, y1, x2, y2 = coords
        
        # 矩形本体
        draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
        draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
        
        # 四隅の円
        draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
        draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
        draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
        draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)
    
    def _draw_text_with_glow(self, draw, position, text, font, fill=(255, 255, 255), glow_color=(0, 0, 0)):
        """光彩付きテキストを描画（多重影で光彩効果）"""
        x, y = position
        
        # 光彩効果（複数の影を重ねる）
        for offset in [(3, 3), (3, -3), (-3, 3), (-3, -3), (0, 3), (3, 0), (0, -3), (-3, 0)]:
            draw.text((x + offset[0], y + offset[1]), text, font=font, fill=glow_color)
        
        # 本体
        draw.text((x, y), text, font=font, fill=fill)


if __name__ == "__main__":
    writer = ResultStatsWriter()
    
    img = Image.open('test.png')

    img = writer.write_statistics(
        img,
        title="Colors",
        level=12,
        play_style=play_style.sp,
        difficulty=difficulty.another,
        ex_score=2128,
        bp=15,
        max_notes=1258,
        lamp=clear_lamp.fc,
        bpi=1.22,
        sp12_clear=unofficial_difficulty.jiriki_d,
        sp12_hard=unofficial_difficulty.jiriki_e
    )
    img = img.crop((560,0,1920,1080))
    img.save('test_result_custom.png')