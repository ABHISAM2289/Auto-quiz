pipeline {
    agent any

    environment {
        COMPOSE_PROJECT_NAME = "autoquiz"
    }

    stages {
        stage('Clone Repository') {
            steps {
                git branch: 'main', url: 'https://github.com/ABHISAM2289/Auto-quiz.git'
            }
        }

        stage('Stop Existing Containers') {
            steps {
                dir('Auto-quiz') {
                    sh 'docker-compose down || true'
                }
            }
        }

        stage('Build and Deploy') {
            steps {
                withCredentials([
                    file(credentialsId: 'gcloud-service-account', variable: 'GCLOUD_JSON'),
                    string(credentialsId: 'GEMINI_API_SUMMARIZER', variable: 'GEMINI_API_KEY')
                ]) {
                    dir('Auto-quiz') {
                        sh '''
                            export GOOGLE_APPLICATION_CREDENTIALS=$GCLOUD_JSON
                            export GEMINI_API_KEY=$GEMINI_API_KEY

                            # Build and deploy with the shared GEMINI_API_KEY
                            docker-compose build

                            docker-compose up -d
                        '''
                    }
                }
            }
        }
    }

    post {
        failure {
            echo 'Build failed!'
        }
        success {
            echo 'Build and deployment successful!'
        }
    }
}
