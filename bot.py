import os
import asyncio
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

print("=== BOT STARTING ===", flush=True)


# ================= CONFIG =================
print("=== RUN BOT ===", flush=True)

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
CREW_ROLE_IDS = [int(r) for r in os.getenv("CREW_ROLE_IDS").split(",")]

INACTIVE_DAYS = 7
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
        print("✅ Bot ready & slash synced")

bot = CrewBot()

@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}")

# ================= CORE LOGIC =================
def build_pages(guild: discord.Guild):
    now = datetime.now(timezone.utc)
    rows = []

    roles = sorted(
        [guild.get_role(rid) for rid in CREW_ROLE_IDS if guild.get_role(rid)],
        key=lambda r: r.position,
        reverse=True
    )

    for role in roles:
        for m in role.members:
            if m.status != discord.Status.offline:
                status = "🟢 Online"
            else:
                if m.last_message_at:
                    days = (now - m.last_message_at).days
                    status = (
                        f"🔴 Inactive {days} ngày ⚠️"
                        if days >= INACTIVE_DAYS
                        else f"🟡 Offline {days} ngày"
                    )
                else:
                    status = "⚫ Chưa có hoạt động"

            rows.append((role, m, status))

    rows.sort(key=lambda x: x[0].position, reverse=True)

    pages = []
    total_pages = (len(rows) - 1) // PAGE_SIZE + 1

    for i in range(0, len(rows), PAGE_SIZE):
        chunk = rows[i:i + PAGE_SIZE]

        embed = discord.Embed(
            title="📊 BÁO CÁO NHÂN SỰ CREW",
            description=f"Trang {i//PAGE_SIZE + 1} / {total_pages}",
            color=0x5865F2
        )

        text = ""
        current_role = None
        index = i + 1

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

        pages.append(embed)

    return pages

# ================= PAGINATION VIEW =================
class CrewPaginator(discord.ui.View):
    def __init__(self, pages):
        super().__init__(timeout=300)
        self.pages = pages
        self.index = 0

    async def update(self, interaction):
        await interaction.response.edit_message(
            embed=self.pages[self.index],
            view=self
        )

    @discord.ui.button(label="⬅️ Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, _):
        if self.index > 0:
            self.index -= 1
        await self.update(interaction)

    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, _):
        if self.index < len(self.pages) - 1:
            self.index += 1
        await self.update(interaction)

# ================= SLASH COMMAND =================
@bot.tree.command(
    name="crew_report",
    description="Báo cáo crew (phân trang, theo chức vụ)"
)
@app_commands.checks.has_permissions(administrator=True)
async def crew_report(interaction: discord.Interaction):
    pages = build_pages(interaction.guild)
    view = CrewPaginator(pages)
    await interaction.response.send_message(
        embed=pages[0],
        view=view
    )

# ================= WEEKLY AUTO REPORT =================
@tasks.loop(hours=24)
async def weekly_report():
    now = datetime.now(VN_TZ)

    # Chủ nhật 20:00
    if now.weekday() == 6 and now.hour == 20:
        guild = bot.get_guild(GUILD_ID)
        channel = guild.get_channel(LOG_CHANNEL_ID)

        pages = build_pages(guild)
        await channel.send("📢 **BÁO CÁO NHÂN SỰ CREW HÀNG TUẦN**")
        for embed in pages:
            await channel.send(embed=embed)
            await asyncio.sleep(1)

