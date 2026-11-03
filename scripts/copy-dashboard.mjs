import {mkdir,cp} from 'node:fs/promises';
await mkdir(new URL('../public/',import.meta.url),{recursive:true});
await cp(new URL('../dashboard/dist/',import.meta.url),new URL('../public/',import.meta.url),{recursive:true});
