import {readdir,readFile} from 'node:fs/promises';
import path from 'node:path';
const secret=process.env.OPENAI_API_KEY;
if(!secret)throw new Error('Run with the ignored .env.local file loaded to check artifacts.');
let files=0;
async function scan(directory){for(const entry of await readdir(directory,{withFileTypes:true})){const file=path.join(directory,entry.name);if(entry.isDirectory())await scan(file);else{files++;if(/^\.env|^\.dev\.vars/.test(entry.name))throw new Error(`Local environment file in artifact: ${file}`);const data=await readFile(file);if(data.includes(Buffer.from(secret)))throw new Error(`Secret detected in artifact: ${file}`);}}}
await scan('dist');console.log(`Artifact scan passed: ${files} files; no local key or environment files found.`);
