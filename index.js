const { Telegraf } = require('telegraf');
const ytdl = require('ytdl-core');
const fs = require('fs');
const path = require('path');

const BOT_TOKEN = process.env.BOT_TOKEN;
if (!BOT_TOKEN) throw new Error('BOT_TOKEN is not set!');

const bot = new Telegraf(BOT_TOKEN);

bot.start((ctx) => ctx.reply('Welcome! Send me a YouTube link to download the video.'));

bot.on('text', async (ctx) => {
  const url = ctx.message.text;
  if (!ytdl.validateURL(url)) {
    return ctx.reply('Please send a valid YouTube URL.');
  }

  let statusMessage;
  let filePath;
  try {
    statusMessage = await ctx.reply('Processing...');
    const info = await ytdl.getInfo(url);
    const format = ytdl.chooseFormat(info.formats, { 
      quality: 'lowestvideo', 
      filter: (f) => f.container === 'mp4' && f.hasAudio && f.hasVideo 
    });

    if (!format) {
      return ctx.telegram.editMessageText(ctx.chat.id, statusMessage.message_id, undefined, 'Sorry, a downloadable MP4 format was not found.');
    }
    
    if (format.contentLength > 50 * 1024 * 1024) {
        return ctx.telegram.editMessageText(ctx.chat.id, statusMessage.message_id, undefined, 'Video is too large (over 50MB). Please try another one.');
    }

    await ctx.telegram.editMessageText(ctx.chat.id, statusMessage.message_id, undefined, 'Downloading video...');
    const videoId = ytdl.getVideoID(url);
    filePath = path.join(__dirname, `${videoId}.mp4`);
    
    const downloadStream = ytdl(url, { format });
    const fileStream = fs.createWriteStream(filePath);
    await new Promise((resolve, reject) => {
        downloadStream.pipe(fileStream);
        fileStream.on('finish', resolve);
        fileStream.on('error', reject);
    });

    await ctx.telegram.editMessageText(ctx.chat.id, statusMessage.message_id, undefined, 'Uploading to Telegram...');
    await ctx.replyWithVideo({ source: filePath });
    await ctx.telegram.deleteMessage(ctx.chat.id, statusMessage.message_id);

  } catch (error) {
    console.error(error);
    if (statusMessage) {
        ctx.telegram.editMessageText(ctx.chat.id, statusMessage.message_id, undefined, 'An error occurred. The video might be private or too large.');
    } else {
        ctx.reply('An error occurred. Please try again.');
    }
  } finally {
    if (filePath && fs.existsSync(filePath)) {
      fs.unlinkSync(filePath); // File delete ho jayegi yahan se
    }
  }
});

bot.launch(() => console.log('Bot is running...'));

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
