import {env} from 'cloudflare:workers';
export const dynamic='force-dynamic';
export async function GET(request:Request){const signedIn=!!request.headers.get('oai-authenticated-user-id');return Response.json({configured:signedIn&&!!env.OPENAI_API_KEY,signInRequired:!signedIn,mode:'hosted-agent',model:'gpt-6-luna',dailyRequests:10,monthlyRequests:100},{headers:{'Cache-Control':'no-store'}});}
