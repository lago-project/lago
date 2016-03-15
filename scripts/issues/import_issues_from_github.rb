#!/usr/bin/env ruby
require 'json'
require 'rest-client'

puts 'Creating User Stories from github issutes.. STARTED!'

#getting github's token: https://help.github.com/articles/creating-an-access-token-for-command-line-use
github_token = "<your github api token comes here>"

#github params
github = {
    :url => 'https://api.github.com/repos/lago-project/lago/issues',
    :token => github_token,
}

#Getting taiga's token: 
taiga_username = '<your taiga user here>'
taiga_password = '<your taiga pass here>'
auth = RestClient.post(
    'https://api.taiga.io/api/v1/auth',
    {
        :type => 'normal',
        :username => taiga_username,
        :password => taiga_password
    }.to_json,
    :content_type => :json,
)
taiga_token = JSON.parse(auth)['auth_token']
puts "Got taiga token #{taiga_token}"

#replace with the taiga project id
taiga_project_id = '114180'

#taiga params
taiga = {
    :url => 'https://api.taiga.io/api/v1/issues',
    :token => "Bearer #{taiga_token}",
    :project_id => taiga_project_id,
}

puts 'Loading Issues from Github..'
pages = []
page_num = 1
response = RestClient::Request.execute(
    method: :get,
    url: github[:url],
    timeout: 10,
    headers: {
        params: {
            Authorization: github[:token],
        }
    }
)
while response.headers[:link].include? 'rel="next"' do
    pages << JSON.parse(response)
    page_num += 1
    response = RestClient::Request.execute(
        method: :get,
        url: github[:url],
        timeout: 10,
        headers: {
            params: {
                Authorization: github[:token],
                page: page_num,
            }
        }
    )
end

pages << JSON.parse(response)

pages.each do |page|
    puts "Creating User Stories on Taiga.."
    page.each do |issue|
        # import only the issues older than this one, the others are added by
        # the taiga-gh sync
        if issue['number'] < 159 then
            puts "Creating User Story on Taiga with subject: #{issue['number']} - #{issue['title']}"
            #" and description: #{issue['body']}"
            RestClient.post(
                taiga[:url],
                {
                    :project => taiga[:project_id],
                    :subject => issue['title'],
                    :description => issue['body'],
                    :external_reference => [:github, issue['html_url']],

                }.to_json,
                {
                    :content_type => :json,
                    :Authorization => taiga[:token]
                }
            )
        else
            puts "Skipping issue #{issue['number']} - #{issue['title']}"
        end
    end
    puts "OK!"
end
