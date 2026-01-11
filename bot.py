import os
import asyncio
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

# ================= START LOG =================
print("=== BOT STARTING ===", flush=True)

# ================= CONFIG =================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
CREW_ROLE_IDS = [int(r) for r in os.getenv("CREW_ROLE_IDS").split(",")]

INACTIVE_DAYS = int(os.getenv("INACTIVE_DAYS", 7))
PAGE_SIZE = 10
VN_TZ = timezone(timedelta(hours=7))

intents = discord.Intents.default()
intents.members = True
intents.presences = True

class CrewBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        weekly_report.start()
        print("✅ Bot ready & slash synced", flush=True)

bot = CrewBot()

@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}", flush=True)

# ================= COLLECT DATA (NO LAG) =================
async def collect_rows(guild: discord.Guild):
    now = datetime.now(timezone.utc)
    rows = []
    counter = 0

    roles = sorted(
        [guild.get_role(rid) for rid in CREW_ROLE_IDS if guild.get_role(rid)],
        key=lambda r: r.position,
        reverse=True
    )

    for role in roles:
        for member in role.members:
            counter += 1
            if counter % 25 == 0:
                await asyncio.sleep(0)  # 🔥 NHẢ CPU → KHÔNG LAG

            if member.status != discord.Status.offline:
                status = "🟢 Online"
            else:
                days = (now - member.last_message_at).days if member.last_message_at else 999
                status = (
                    f"🔴 Inactive {days} ngày ⚠️"
                    if days >= INACTIVE_DAYS
                    else f"🟡 Offline {days} ngày"
                )

            rows.append((role, member, status))

    return rows

# ================= PAGINATION (LAZY LOAD) =================
class CrewPaginator(discord.ui.View):
    def __init__(self, rows):
        super().__init__(timeout=300)
        self.rows = rows
        self.page = 0
        self.max_page = (len(rows) - 1) // PAGE_SIZE

    def build_page(self):
        start = self.page * PAGE_SIZE
        end = start + PAGE_SIZE
        chunk = self.rows[start:end]

        embed = discord.Embed(
            title="📊 BÁO CÁO NHÂN SỰ CREW",
            description=f"Trang {self.page + 1} / {self.max_page + 1}",
            color=0x5865F2
        )

        text = ""
        current_role = None
        index = start + 1

        for role, member, status in chunk:
            if role != current_role:
                text += f"\n**{role.name}**\n"
                current_role = role

            text += f"{index}. {member.display_name} | {status}\n"
            index += 1

        embed.add_field(name="👥 Danh sách", value=text, inline=False)
        embed.add_field(
            name="📝 Trạng thái – Điều kiện",
            value=(
                "🟢 Online : Có mặt / vừa chat\n"
                "🟡 Offline : Không chat 1–6 ngày\n"
                "🔴 Inactive : Không chat ≥7 ngày"
            ),
            inline=False
        )
        return embed

    @discord.ui.button(label="⬅️ Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, _):
        self.page = max(0, self.page - 1)
        await interaction.response.edit_message(
            embed=self.build_page(),
            view=self
        )

    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, _):
        self.page = min(self.max_page, self.page + 1)
        await interaction.response.edit_message(
            embed=self.build_page(),
            view=self
        )

# ================= SLASH COMMAND =================
@bot.tree.command(
    name="crew_report",
    description="Báo cáo crew (tối ưu cho server đông)"
)
@app_commands.checks.has_permissions(administrator=True)
async def crew_report(interaction: discord.Interaction):

    # ⏳ giữ interaction sống
    await interaction.response.defer(thinking=True)

    rows = await collect_rows(interaction.guild)

    if not rows:
        await interaction.followup.send("❌ Không có dữ liệu crew")
        return

    view = CrewPaginator(rows)

    await interaction.followup.send(
        embed=view.build_page(),
        view=view
    )

# ================= WEEKLY AUTO REPORT =================
@tasks.loop(hours=24)
async def weekly_report():
    now = datetime.now(VN_TZ)
    if now.weekday() != 6 or now.hour != 20:
        return

    guild = bot.get_guild(GUILD_ID)
    channel = guild.get_channel(LOG_CHANNEL_ID)

    if not guild or not channel:
        return

    rows = await collect_rows(guild)

    await channel.send("📢 **BÁO CÁO NHÂN SỰ CREW HÀNG TUẦN**")

    for role, member, status in rows:
        await channel.send(f"{member.display_name} | {role.name} | {status}")
        await asyncio.sleep(0.3)

# ================= RUN =================
print("=== TRY LOGIN DISCORD ===", flush=True)

try:
    bot.run(TOKEN)
except Exception as e:
    print("❌ BOT CRASH:", e, flush=True)
    raise
